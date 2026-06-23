# hifisampler

这是 hifisampler 的 Windows portable fork，目标是让 OpenUTAU 用户尽可能简单地使用。

当前主要文档已经改为 portable-first，并以英文维护：

```text
README.md
```

推荐使用方式：

1. 从 Releases 下载 `hifisampler-portable-windows-cpu-<version>.zip`。
2. 解压到普通用户目录。
3. 运行 `HifisamplerManager.exe`。
4. 点击 `Prepare Portable`。
5. 选择模型。
6. 点击 `Install to OpenUTAU`。
7. 点击 `Start Server`。
8. 在 OpenUTAU 中选择 `hifisampler` resampler。

不需要管理员权限，不需要手动编辑 YAML，不需要 `mklink`。

详细说明请查看 `README.md`。
