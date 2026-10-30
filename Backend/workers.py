from concurrent.futures import ThreadPoolExecutor

from images import resize_file

# Bounded worker threads. Mail keeps its own thread so SMTP cannot fill this pool.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="zivo-image")


def resize_upload(path):
    """Run resize on a worker and wait so the stored file is final before use."""
    future = _pool.submit(resize_file, path)
    future.result()
