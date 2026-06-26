import logging
import os
import pickle
import threading
from pathlib import Path
from typing import Dict, Any
import numpy as np


class ReadWriteLock:
    def __init__(self):
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0

    def acquire_read(self):
        self._read_ready.acquire()
        try:
            self._readers += 1
        finally:
            self._read_ready.release()

    def release_read(self):
        self._read_ready.acquire()
        try:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()
        finally:
            self._read_ready.release()

    def acquire_write(self):
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()

    def release_write(self):
        self._read_ready.release()


class RWLockContext:
    def __init__(self, lock: ReadWriteLock, write_mode: bool = False):
        self.lock = lock
        self.write_mode = write_mode

    def __enter__(self):
        if self.write_mode:
            self.lock.acquire_write()
        else:
            self.lock.acquire_read()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.write_mode:
            self.lock.release_write()
        else:
            self.lock.release_read()


class CacheManager:
    def __init__(self):
        self._locks: Dict[str, ReadWriteLock] = {}
        self._locks_lock = threading.Lock()

    def get_lock(self, cache_path: Path) -> ReadWriteLock:
        cache_key = str(cache_path.resolve())
        with self._locks_lock:
            if cache_key not in self._locks:
                self._locks[cache_key] = ReadWriteLock()
            return self._locks[cache_key]

    def read_lock(self, cache_path: Path):
        return RWLockContext(self.get_lock(cache_path), write_mode=False)

    def write_lock(self, cache_path: Path):
        return RWLockContext(self.get_lock(cache_path), write_mode=True)

    def load_features_cache(self, cache_path: Path, force_generate: bool = False) -> Any:
        if force_generate:
            return None

        with self.read_lock(cache_path):
            if cache_path.exists():
                try:
                    features = np.load(str(cache_path))
                    logging.info(f'Cache loaded successfully: {cache_path.name}')
                    return features
                except (EOFError, OSError, ValueError) as e:
                    logging.warning(
                        f'Failed to load cache {cache_path.name}: '
                        f'{type(e).__name__}: {e}'
                    )
        return None

    def load_hnsep_cache(self, cache_path: Path, device: str, force_generate: bool = False) -> Any:
        """Load HN-SEP cache via pickle. `device` kept for API compat, ignored."""
        if force_generate:
            return None

        with self.read_lock(cache_path):
            if cache_path.exists():
                try:
                    with open(str(cache_path), 'rb') as f:
                        data = pickle.load(f)
                    logging.info(f'Hnsep cache loaded successfully: {cache_path.name}')
                    return data
                except Exception as e:
                    logging.warning(
                        f'Failed to load hnsep cache {cache_path.name}: '
                        f'{type(e).__name__}: {e}'
                    )
        return None

    def save_features_cache(self, cache_path: Path, features: Dict[str, Any]):
        with self.write_lock(cache_path):
            if cache_path.exists():
                try:
                    existing_features = np.load(str(cache_path))
                    logging.info(f'Cache already exists, using existing: {cache_path.name}')
                    return existing_features
                except Exception:
                    pass

            temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
            try:
                np.savez_compressed(str(temp_path), **features)
                os.replace(str(temp_path) + '.npz', str(cache_path))
                logging.info(f'Features saved successfully to {cache_path}')
                return features
            except Exception as e:
                logging.error(f'Error saving cache {cache_path}: {e}', exc_info=True)
                if temp_path.exists():
                    try:
                        os.remove(str(temp_path) + '.npz')
                    except OSError:
                        pass
                raise

    def save_hnsep_cache(self, cache_path: Path, data: Any):
        """Save HN-SEP cache via pickle."""
        with self.write_lock(cache_path):
            if cache_path.exists():
                try:
                    with open(str(cache_path), 'rb') as f:
                        existing_data = pickle.load(f)
                    logging.info(
                        f'Hnsep cache already exists, using existing: {cache_path.name}'
                    )
                    return existing_data
                except Exception:
                    pass

            temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
            try:
                with open(str(temp_path), 'wb') as f:
                    pickle.dump(data, f)
                os.replace(str(temp_path), str(cache_path))
                logging.info(f'Hnsep data saved successfully to {cache_path}')
                return data
            except Exception as e:
                logging.error(f'Error saving hnsep cache {cache_path}: {e}', exc_info=True)
                if temp_path.exists():
                    try:
                        os.remove(str(temp_path))
                    except OSError:
                        pass
                raise


cache_manager = CacheManager()
