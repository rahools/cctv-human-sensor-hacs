from __future__ import annotations

from typing import Final

DOMAIN: Final = "hunch"
PLATFORMS: Final = ["binary_sensor"]
PANEL_URL: Final = "/hunch/frontend/hunch-panel.js"

CONF_SERVER_URL: Final = "server_url"
CONF_SERVER_ID: Final = "server_id"
CONF_TOKEN: Final = "token"
CONF_VERIFY_TLS: Final = "verify_tls"
CONF_CAMERA_NAME: Final = "camera_name"
CONF_SNAPSHOT_URL: Final = "snapshot_url"
CONF_AUTH_TYPE: Final = "auth_type"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_MOTION_ENABLED: Final = "motion_enabled"
CONF_TRACKING_ENABLED: Final = "tracking_enabled"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_DETECTION_INTERVAL: Final = "detection_interval"
CONF_THRESHOLD: Final = "threshold"
CONF_CLEAR_DELAY: Final = "clear_delay"
CONF_PIXEL_THRESHOLD: Final = "pixel_threshold"
CONF_AREA_THRESHOLD: Final = "area_threshold"
CONF_TRIGGER_FRAMES: Final = "trigger_frames"
CONF_MOTION_END_DELAY: Final = "motion_end_delay"
CONF_ZONE: Final = "zone"

AUTH_AUTO: Final = "auto"
AUTH_BASIC: Final = "basic"
AUTH_DIGEST: Final = "digest"
AUTH_NONE: Final = "none"
SUBENTRY_TYPE_CAMERA: Final = "camera"

DEFAULT_POLL_INTERVAL: Final = 1.0
DEFAULT_DETECTION_INTERVAL: Final = 1.0
DEFAULT_THRESHOLD: Final = 0.5
DEFAULT_CLEAR_DELAY: Final = 5.0
DEFAULT_PIXEL_THRESHOLD: Final = 25
DEFAULT_AREA_THRESHOLD: Final = 0.01
DEFAULT_TRIGGER_FRAMES: Final = 1
DEFAULT_MOTION_END_DELAY: Final = 3.0
MAX_SNAPSHOT_BYTES: Final = 10 * 1024 * 1024
