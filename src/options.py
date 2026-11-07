"""The options the admin page can change. Each can still start from its environment variable; a saved value wins."""

from settings import Setting

SETTINGS = [
    Setting("update_check_hours", "Check for updates every (hours)", "float", 6.0, "SERVICE_UPDATE_CHECK_HOURS", 0, 720,
            help="0 = only when you press Check now"),
    Setting("max_inflight", "Calls allowed to wait for the model", "int", 0, "SERVICE_MAX_INFLIGHT", 0, 10000,
            help="Per replica; more get 429. 0 = 4"),
    Setting("cache_size", "Answers kept per replica", "int", 256, "SERVICE_CACHE_SIZE", 0, 100000,
            help="The last answers for the same image and mode, sent again without recognizing. Recognition is deterministic, so every request is kept. 0 = off"),
    Setting("max_upload_mb", "Largest image (MB)", "float", 10.0, "SERVICE_MAX_UPLOAD_MB", 0.1, 100,
            help="A bigger body gets 413"),
    Setting("max_pixels", "Most decoded pixels", "int", 16_000_000, "SERVICE_MAX_PIXELS", 1, 50_000_000,
            help="Checked before the image is decoded into memory; more gets 422"),
    Setting("timeout_s", "Time limit per call (seconds)", "float", 110.0, "SERVICE_TIMEOUT_S", 0.1, 600,
            help="A caller's own timeout query can only shorten it. Keep it under what the caller waits"),
    Setting("concurrency", "Recognitions at once per replica", "int", 2, "SERVICE_CONCURRENCY", 1, 16, restart=True,
            help="Each runs its own Tesseract process. Set CPU threads low (1 to 2) when this is more than 1"),
    Setting("warm", "Read the model files at start", "bool", True, "SERVICE_WARM", restart=True),
]
