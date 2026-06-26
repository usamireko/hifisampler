using System;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.IO;
using System.Diagnostics;

class Program
{
    // Static HttpClient for actual POST requests
    static readonly HttpClient PostClient = new HttpClient() { Timeout = TimeSpan.FromSeconds(180) };
    // Factory for short-timeout clients for readiness checks
    static readonly Func<HttpClient> CheckClientFactory = () => new HttpClient() { Timeout = TimeSpan.FromSeconds(2) };

    static readonly int TargetPort = 8572;
    // start.bat for Windows, start.sh for Linux/Mac
    static readonly string LauncherScriptName = OperatingSystem.IsWindows() ? "start.bat" : "start.sh";
    private const string ServerStartupMutexName = "Global\\HifiSamplerServerStartupMutex_DCL_8572"; // Unique name for DCL version

    // --- Main Entry Point ---
    static async Task Main(string[] args)
    {
        if (args.Length < 1)
        {
            Console.Error.WriteLine("[Main] No arguments provided.");
            Environment.Exit(1);
        }

        bool proceedToCommunication = false;
        bool errorOccurred = false;
        string errorMessage = "";

        // --- Phase 1: Quick Readiness Check (No Lock) ---
        Console.WriteLine("[Main] Performing initial readiness check (no lock)...");
        if (await IsServerReady(TargetPort))
        {
            Console.WriteLine("[Main] Initial check PASSED. Server is ready.");
            proceedToCommunication = true;
        }
        else
        {
            Console.WriteLine("[Main] Initial check FAILED. Server not ready. Proceeding with mutex...");

            // --- Phase 2: Acquire Mutex and Double-Check ---
            using (var mutex = new Mutex(false, ServerStartupMutexName))
            {
                bool mutexAcquired = false;
                bool mutexOwned = false; // Track if we actually own the mutex
                try
                {
                    try
                    {
                        mutexAcquired = mutex.WaitOne(TimeSpan.FromSeconds(5));
                        mutexOwned = mutexAcquired; // Normal acquisition
                    }
                    catch (AbandonedMutexException)
                    {
                        Console.WriteLine("[Main] Warning: Acquired abandoned mutex. Previous owner likely crashed.");
                        mutexAcquired = true;
                        mutexOwned = true; // We own it after abandoned mutex exception
                    }

                    // --- Phase 3: Actions Inside Mutex (if acquired) ---
                    if (mutexAcquired)
                    {
                        Console.WriteLine("[Main] Mutex acquired. Performing second readiness check...");

                        // ** Double-Check **
                        if (await IsServerReady(TargetPort))
                        {
                            Console.WriteLine("[Main] Second check PASSED (inside mutex). Server is ready.");
                            proceedToCommunication = true; // Mark ready, will skip final wait
                        }
                        else
                        {
                            Console.WriteLine("[Main] Second check FAILED (inside mutex). Checking port...");
                            // Server still not ready, check if someone else might be launching it
                            if (!IsPortInUse(TargetPort))
                            {
                                // Port is free - WE MUST LAUNCH
                                Console.WriteLine($"[Main] Port {TargetPort} is free. This instance will launch the server.");
                                string exeDir = AppContext.BaseDirectory;
                                string scriptPath = Path.Combine(exeDir, LauncherScriptName);

                                if (!File.Exists(scriptPath))
                                {
                                    errorMessage = $"Error: {LauncherScriptName} not found at '{scriptPath}'.";
                                    errorOccurred = true;
                                }
                                else
                                {
                                    try
                                    {
                                        LaunchServerLauncher(scriptPath);
                                        Console.WriteLine("[Main] Launch initiated. Performing initial wait *inside* mutex...");

                                        // Initial wait while holding the lock
                                        bool initialWaitOk = await WaitForServerToStart(TargetPort, 60, "[InitialWait]");
                                        if (initialWaitOk)
                                        {
                                            Console.WriteLine("[Main] Initial wait successful. Server presumed ready by launcher.");
                                            proceedToCommunication = true; // Our launch succeeded
                                        }
                                        else
                                        {
                                            errorMessage = "Server launched by this instance did not become ready during initial wait.";
                                            errorOccurred = true;
                                        }
                                    }
                                    catch (Exception ex)
                                    {
                                        errorMessage = $"Error during server launch execution: {ex.Message}";
                                        errorOccurred = true;
                                    }
                                }
                            }
                            else
                            {
                                // Port is in use, but not ready. Someone else is launching/initializing.
                                Console.WriteLine($"[Main] Port {TargetPort} is in use, but server not ready. Assuming another instance is handling it.");
                                // proceedToCommunication remains false - needs final wait outside lock
                            }
                        }
                    }
                    else // Mutex not acquired (timed out)
                    {
                        Console.WriteLine("[Main] Mutex not acquired (timeout). Assuming another instance handled checks/launch.");
                        // proceedToCommunication remains false - needs final wait outside lock
                    }
                }
                catch (Exception ex) // Catch unexpected errors during mutex-protected logic
                {
                    errorMessage = $"Unexpected error during mutex protected checks: {ex.Message}";
                    errorOccurred = true;
                }
                finally
                {
                    // Improved mutex release with better error handling
                    if (mutexOwned)
                    {
                        bool releaseSucceeded = false;
                        try
                        {
                            mutex.ReleaseMutex();
                            Console.WriteLine("[Main] Mutex released successfully.");
                            releaseSucceeded = true;
                        }
                        catch (ApplicationException ex)
                        {
                            // This usually means the mutex was already released or we don't own it
                            Console.WriteLine($"[Main] ApplicationException during mutex release (usually safe to ignore): {ex.Message}");
                            releaseSucceeded = true; // Treat as success since mutex is effectively released
                        }
                        catch (ObjectDisposedException ex)
                        {
                            // Mutex was disposed, which means it's effectively released
                            Console.WriteLine($"[Main] Mutex was already disposed: {ex.Message}");
                            releaseSucceeded = true;
                        }
                        catch (Exception ex)
                        {
                            Console.Error.WriteLine($"[Main] Unexpected error releasing mutex: {ex.GetType().Name} - {ex.Message}");
                            // Don't treat as success - this might be a real problem
                        }

                        if (releaseSucceeded)
                        {
                            mutexOwned = false; // Mark as no longer owned
                        }
                        else
                        {
                            Console.Error.WriteLine("[Main] Warning: Failed to properly release mutex. This may affect future launches.");
                        }
                    }
                }
            } // --- End of using (Mutex) block ---
        }

        // --- Phase 4: Handle Errors or Perform Final Wait ---
        if (errorOccurred)
        {
            Console.Error.WriteLine($"[Main] Exiting due to critical error: {errorMessage}");
            Environment.Exit(1);
        }

        // Perform final wait ONLY if the server wasn't confirmed ready earlier
        if (!proceedToCommunication)
        {
            Console.WriteLine("[Main] Performing final wait for server readiness confirmation...");
            bool finalReadinessCheck = await WaitForServerToStart(TargetPort, 95, "[FinalWait]");

            if (!finalReadinessCheck)
            {
                Console.Error.WriteLine("[Main] Error: Server failed final readiness check.");
                Environment.Exit(1);
            }
            Console.WriteLine("[Main] Final readiness check successful.");
            proceedToCommunication = true; // Now we can proceed
        }

        // --- Phase 5: Communicate ---
        if (proceedToCommunication)
        {
            Console.WriteLine("[Main] Proceeding to communication...");
            await CommunicateWithServer(args);
            Console.WriteLine("[Main] Task completed successfully.");
        }
        else
        {
            // Should be unreachable if logic is correct
            Console.Error.WriteLine("[Main] Error: Logic flaw - Communication attempted without readiness confirmation.");
            Environment.Exit(1);
        }
    }

    // --- Communication Function (with Retries) ---
    static async Task CommunicateWithServer(string[] args)
    {
        int maxRetries = 2;
        int retryDelayMs = 800;
        HttpResponseMessage response = null;
        bool requestSucceeded = false;
        for (int attempt = 1; attempt <= maxRetries + 1; attempt++)
        {
            try
            {
                var postFields = string.Join(" ", args);
                var content = new StringContent(postFields, Encoding.UTF8, "application/x-www-form-urlencoded");
                Console.WriteLine($"[Communicate] Attempting POST (Attempt {attempt}/{maxRetries + 1})...");
                response = await PostClient.PostAsync($"http://127.0.0.1:{TargetPort}/", content);
                if (response.IsSuccessStatusCode)
                {
                    Console.WriteLine($"[Communicate] Success (Attempt {attempt}, Status: {(int)response.StatusCode})");
                    requestSucceeded = true;
                    break;
                }
                else
                {
                    string responseBody = response.Content == null ? "[No Body]" : await response.Content.ReadAsStringAsync();
                    Console.Error.WriteLine($"[Communicate] Error (Attempt {attempt}): Server Status: {(int)response.StatusCode} {response.ReasonPhrase}");
                    Console.Error.WriteLine($"[Communicate] Response Body: {responseBody.Substring(0, Math.Min(responseBody.Length, 500))}{(responseBody.Length > 500 ? "..." : "")}");
                    if ((response.StatusCode == HttpStatusCode.ServiceUnavailable || response.StatusCode == HttpStatusCode.InternalServerError) && attempt <= maxRetries)
                    {
                        Console.WriteLine($"[Communicate] Retrying potential transient error {(int)response.StatusCode}...");
                    }
                    else
                    {
                        break;
                    }
                }
            }
            catch (HttpRequestException ex)
            {
                Console.Error.WriteLine($"[Communicate] Network Error (Attempt {attempt}): {ex.Message}");
            }
            catch (TaskCanceledException ex)
            {
                if (ex.InnerException is TimeoutException || !ex.CancellationToken.IsCancellationRequested)
                {
                    Console.Error.WriteLine($"[Communicate] Request Timed Out (Attempt {attempt}).");
                    break;
                }
                else
                {
                    Console.Error.WriteLine($"[Communicate] Request Cancelled (Attempt {attempt}): {ex.Message}");
                    break;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[Communicate] Unexpected Error (Attempt {attempt}): {ex.GetType().Name} - {ex.Message}");
                break;
            }
            if (!requestSucceeded && attempt <= maxRetries)
            {
                Console.WriteLine($"[Communicate] Waiting {retryDelayMs}ms before retry #{attempt + 1}...");
                await Task.Delay(retryDelayMs);
            }
        }
        if (!requestSucceeded)
        {
            Console.Error.WriteLine("[Communicate] Failed after all attempts.");
            Environment.Exit(1);
        }
    }

    // --- Readiness Check Function (GET /) ---
    static async Task<bool> IsServerReady(int port)
    {
        HttpClient checkClient = null;
        try
        {
            checkClient = CheckClientFactory();
            HttpResponseMessage response = await checkClient.GetAsync($"http://127.0.0.1:{port}/");
            return response.StatusCode == HttpStatusCode.OK;
        }
        catch
        {
            return false;
        }
        finally
        {
            checkClient?.Dispose();
        }
    }

    // --- Wait Function (Polls IsServerReady) ---
    static async Task<bool> WaitForServerToStart(int port, int timeoutSeconds, string logPrefix = "[WaitForServer]")
    {
        Console.WriteLine($"{logPrefix} Waiting up to {timeoutSeconds}s for server at port {port} to be ready (GET / returns 200 OK)...");
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
        var sw = Stopwatch.StartNew();
        bool loggedPortInfo = false;
        while (!cts.IsCancellationRequested)
        {
            if (await IsServerReady(port))
            {
                Console.WriteLine($"\n{logPrefix} Server became ready after {sw.Elapsed.TotalSeconds:F1}s.");
                return true;
            }
            if (!loggedPortInfo && sw.Elapsed.TotalSeconds > 2)
            {
                loggedPortInfo = true;
                if (IsPortInUse(port))
                {
                    Console.WriteLine($"{logPrefix} Port {port} is open, waiting for application readiness...");
                }
                else
                {
                    Console.WriteLine($"{logPrefix} Port {port} is not open yet...");
                }
            }
            if ((int)sw.Elapsed.TotalSeconds % 5 == 1) Console.Write(".");
            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(500), cts.Token);
            }
            catch (TaskCanceledException)
            {
                break;
            }
        }
        Console.WriteLine($"\n{logPrefix} Server did not become ready within {timeoutSeconds}s.");
        return false;
    }

    // --- Basic Port Check (Used ONLY inside mutex) ---
    static bool IsPortInUse(int port)
    {
        const int timeoutMs = 150;
        Socket socket = null;
        try
        {
            socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            var result = socket.BeginConnect("127.0.0.1", port, null, null);
            bool success = result.AsyncWaitHandle.WaitOne(timeoutMs);
            if (success)
            {
                socket.EndConnect(result);
                return true;
            }
            else
            {
                return false;
            }
        }
        catch
        {
            return false;
        }
        finally
        {
            socket?.Close();
            socket?.Dispose();
        }
    }

    // --- Server Launcher ---
    static void LaunchServerLauncher(string launcherScriptPath)
    {
        if (string.IsNullOrEmpty(launcherScriptPath) || !File.Exists(launcherScriptPath))
        {
            throw new FileNotFoundException("Launcher script path invalid.", launcherScriptPath);
        }
        Console.WriteLine($"[LaunchServerLauncher] Launching server: '{launcherScriptPath}'");
        string workingDir = Path.GetDirectoryName(launcherScriptPath) ?? ".";
        try
        {
            if (OperatingSystem.IsWindows())
            {
                // Run silently, no terminal window
                string pythonExe = Path.Combine(workingDir, "runtime", "python.exe");
                string serverScript = Path.Combine(workingDir, "hifiserver.py");
                string logDir = Path.Combine(workingDir, "logs");
                Directory.CreateDirectory(logDir);
                string logFile = Path.Combine(logDir, "server.log");
                Process.Start(new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = $"\"{serverScript}\"",
                    WorkingDirectory = workingDir,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                });
                Console.WriteLine("[LaunchServerLauncher] Server started (background, no window).");
            }
            else if (OperatingSystem.IsLinux() || OperatingSystem.IsMacOS())
            {
                string scriptCmd = $"echo Starting HifiSampler Server... ; \\\"{launcherScriptPath}\\\" ; echo ; echo Server process finished. Press Enter to close terminal. ; read -p ''";
                string bashCmd = $"bash -c '{scriptCmd}'";
                var terminals = new[] { new { Name = "gnome-terminal", Arg = "--", Cmd = bashCmd }, new { Name = "konsole", Arg = "-e", Cmd = bashCmd }, new { Name = "xfce4-terminal", Arg = "--command", Cmd = bashCmd }, new { Name = "mate-terminal", Arg = "-e", Cmd = bashCmd }, new { Name = "terminator", Arg = "-e", Cmd = bashCmd }, new { Name = "lxterminal", Arg = "-e", Cmd = bashCmd }, new { Name = "xterm", Arg = "-e", Cmd = bashCmd } };
                bool launched = false;
                foreach (var term in terminals)
                {
                    Process checkProc = null;
                    try
                    {
                        ProcessStartInfo checkPsi = new ProcessStartInfo("which", term.Name) { RedirectStandardOutput = true, UseShellExecute = false, CreateNoWindow = true };
                        checkProc = Process.Start(checkPsi);
                        checkProc?.WaitForExit(500);
                        if (checkProc?.ExitCode == 0)
                        {
                            Console.WriteLine($"[LaunchServerLauncher] Found terminal: {term.Name}. Launching...");
                            Process.Start(new ProcessStartInfo { FileName = term.Name, Arguments = $"{term.Arg} {term.Cmd}", WorkingDirectory = workingDir, UseShellExecute = true, CreateNoWindow = false });
                            launched = true;
                            break;
                        }
                    }
                    catch { }
                    finally
                    {
                        checkProc?.Dispose();
                    }
                }
                if (!launched) throw new NotSupportedException("Could not find supported graphical terminal.");
            }
            else
            {
                throw new PlatformNotSupportedException("Unsupported OS for launching server window.");
            }
            Console.WriteLine($"[LaunchServerLauncher] Server launch command issued.");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[LaunchServerLauncher] Launch failure: {ex.Message}");
            throw;
        }
    }
}