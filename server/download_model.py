from huggingface_hub import snapshot_download

snapshot_download(
    "google/embeddinggemma-2",
    revision="914f7f89142e33e77833254d9c9b90c3cef7303b",
    allow_patterns=["config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors"],
)
