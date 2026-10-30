# Hunch Human Detection for Home Assistant

Run local human detection for CCTV snapshot sources. The project contains:

- A Dockerized [Hunch](https://github.com/undrgrnd-labs/hunch) server using EmbeddingGemma 2 on the CPU.
- A Home Assistant integration with multiple camera sources, motion filtering, detection zones, and occupancy binary sensors.
- A visual zone editor for choosing the part of each frame used by both motion and human detection.

The detection API returns only a boolean and a confidence score:

```json
{
  "human": true,
  "confidence": 0.943948
}
```

## Before you start

You need:

- Docker with Docker Compose.
- Home Assistant 2026.10.0 or newer running in Docker.
- A camera that returns a JPEG or PNG snapshot over HTTP or HTTPS. RTSP streams are not accepted directly.
- Approximately 2 GB of free memory for the detection server and 1.4 GB of disk space for its model. No GPU is required.

Keep the detection server on your LAN. Do not expose it to the internet or forward its port through your router.

## 1. Download the project

On the Docker host:

```bash
git clone https://github.com/rahools/cctv-human-sensor-hacs.git
cd cctv-human-sensor-hacs
```

## 2. Configure the detection server

Create a file named `.env` in the project directory:

```dotenv
HUNCH_TOKEN=replace-with-a-long-random-token
HUNCH_THRESHOLD=0.5
HUNCH_IMAGE_TOKENS=70
```

Use a different random token for your installation. You can generate one with:

```bash
openssl rand -hex 32
```

- `HUNCH_TOKEN` protects detection and status requests. Health and readiness endpoints remain unauthenticated.
- `HUNCH_THRESHOLD` is the default human-confidence threshold. Each camera can override it in Home Assistant.
- `HUNCH_IMAGE_TOKENS` controls image detail. Start with `70`; higher values may help with small or distant people but reduce throughput.

The `.env` file is ignored by Git. Do not commit it or share its contents.

## 3. Download the model and start Docker Compose

GitHub Actions publishes `ghcr.io/rahools/cctv-human-sensor-hacs:latest` for `linux/amd64` and `linux/arm64` after changes reach `main`. Version tags such as `v1.0.0` also produce matching image tags. No local Rust or Python build is required.

Pull the published image:

```bash
docker compose pull
```

If GitHub created the package as private, either make the GHCR package public in its GitHub package settings or authenticate on the server with `docker login ghcr.io` before pulling.

Download the pinned model once:

```bash
docker compose run --rm detector /app/download_model.py
```

Then start the server:

```bash
docker compose up -d
```

The model is stored in the `hunch-models` Docker volume and is not downloaded again on ordinary restarts. Server identity is stored in `hunch-state`.

Check the logs and readiness:

```bash
docker compose logs -f detector
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8765/healthz
curl --fail http://127.0.0.1:8765/readyz
```

Model loading can take a short time. `/readyz` returns HTTP 200 only when inference is available.

To test the complete detection endpoint with a JPEG:

```bash
curl \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: image/jpeg" \
  --data-binary @frame.jpg \
  http://127.0.0.1:8765/v1/detections/human
```

## 4. Find the server URL for Home Assistant

The correct address depends on Docker networking. **When Home Assistant runs in a normal bridge-network container, `localhost` and `127.0.0.1` refer to the Home Assistant container itself, not to the detector.**

| Home Assistant setup | Server URL to enter |
| --- | --- |
| Default Docker bridge network | `http://<docker-host-LAN-IP>:8765` |
| Home Assistant with `network_mode: host` | `http://127.0.0.1:8765` |
| Detector running on another machine | `http://<detector-host-LAN-IP>:8765` |
| Both containers attached to the same custom Docker network | `http://detector:8765` |

For a typical installation, use the Docker host's LAN address, for example `http://192.168.1.20:8765`. Make sure any host firewall allows Home Assistant to reach TCP port `8765`.

## 5. Install the Home Assistant integration

Use either HACS or a manual copy.

### Option A: HACS

1. Open HACS in Home Assistant.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/rahools/cctv-human-sensor-hacs` with type **Integration**.
4. Install **Hunch Human Detection**.
5. Restart Home Assistant:

   ```bash
   docker restart <homeassistant-container-name>
   ```

### Option B: Manual installation

Find the host directory mounted as `/config` in your Home Assistant container. The following example assumes it is `/srv/homeassistant`; change it to match your installation.

Use Git's sparse-checkout mode to download only the Home Assistant component, without the detection server, model tooling, or development files:

```bash
export HA_CONFIG=/srv/homeassistant
git clone --filter=blob:none --sparse \
  https://github.com/rahools/cctv-human-sensor-hacs.git \
  /tmp/cctv-human-sensor-hacs
cd /tmp/cctv-human-sensor-hacs
git sparse-checkout set custom_components/hunch
mkdir -p "$HA_CONFIG/custom_components"
cp -R custom_components/hunch "$HA_CONFIG/custom_components/"
docker restart <homeassistant-container-name>
```

To update a sparse checkout later, run `git pull` in `/tmp/cctv-human-sensor-hacs`, copy `custom_components/hunch` again, and restart Home Assistant.

The resulting path must be:

```text
/srv/homeassistant/custom_components/hunch/manifest.json
```

It must not be nested as `custom_components/hunch/hunch/manifest.json`.

## 6. Connect Home Assistant to the server

1. Open **Settings → Devices & services**.
2. Choose **Add integration** and search for **Hunch Human Detection**.
3. Enter:
   - **Server URL:** the Docker-appropriate URL from the table above.
   - **API token:** the value of `HUNCH_TOKEN` from `.env`.
   - **Verify TLS certificate:** leave enabled for HTTPS with a trusted certificate. Plain LAN HTTP does not use this setting.
4. Submit the form. Home Assistant verifies both the server connection and model readiness.

## 7. Add a Hikvision or other CCTV source

From the configured Hunch server entry, choose **Add CCTV source**.

A typical Hikvision snapshot URL is:

```text
http://192.168.1.50/ISAPI/Streaming/channels/101/picture
```

Check your camera's channel numbering and firmware documentation. Put the camera username and password in their dedicated fields, not in the URL. Hikvision installations commonly need **Digest** authentication; **Auto** can negotiate digest and fall back to basic authentication.

The main settings are:

| Setting | Initial value | Purpose |
| --- | --- | --- |
| Camera name | Required | Names the Home Assistant device and entity |
| Snapshot URL | Required | JPEG or PNG endpoint polled by the integration |
| Only detect humans after motion | Enabled | Avoids inference calls for unchanged frames |
| Keep detecting while a human is present | Enabled | Continues inference without motion until the person leaves |
| Snapshot interval | 1 second | How often the camera image is fetched; 0.5 seconds is supported |
| Detection interval during motion or tracking | 1 second | Maximum inference frequency in the active detection mode |
| Human-confidence threshold | 0.50 | Minimum score for a positive result |
| Clear after continuous negative results | 5 seconds | Negative detection time required before clearing and restoring motion gating |

Advanced options control pixel difference, changed-area ratio, consecutive motion frames, and motion-end delay. Start with the defaults and tune them using footage from your own cameras.

Home Assistant tests the snapshot before saving the source. Each source gets an occupancy entity similar to:

```text
binary_sensor.front_door_human
```

## 8. Draw a detection zone

1. Open **Hunch** in the Home Assistant sidebar.
2. Select a camera and choose **Refresh snapshot**.
3. Drag on the image to draw a rectangle.
4. Drag inside the rectangle to move it, or use its edge and corner handles to resize it.
5. Review the cropped preview and choose **Save zone**.
6. Choose **Use full frame** to remove the crop.

Zones are saved as normalized coordinates, so they survive ordinary resolution changes. Review them if the camera's aspect ratio changes. Currently each camera has one rectangular zone.

The integration crops first, then runs motion analysis and sends only that cropped image to the detection server. Motion outside the zone therefore causes neither motion triggering nor inference.

## 9. Use the sensor in an automation

Example automation YAML:

```yaml
alias: Notify when a person reaches the front door
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door_human
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Front door
      message: A person was detected.
```

A positive result turns the sensor on immediately and enables **human tracking**. While tracking, frames continue going to the model without requiring motion, so a stationary person remains detected. The sensor clears only after negative results continue for the configured delay; it then resets the motion reference and returns to motion gating. Brief negative results do not clear it, and camera or server failures do not count as negative detections.

For lights and other latency-sensitive automations, use a **0.5-second snapshot interval**, a **0.5-second detection interval**, and **1 consecutive motion frame**. Positive detection requires only one result. These settings increase camera traffic and model usage, particularly while a person is being tracked.

Diagnostic entity attributes include `detection_mode`, `last_snapshot_ms`, `last_inference_ms`, `last_detection_queued_ms`, and `last_pipeline_ms`. Use them to determine whether remaining latency comes from the camera, model inference, server queuing, or the complete pipeline.

## Updating

Update the server and integration source:

```bash
cd cctv-human-sensor-hacs
git pull
docker compose pull
docker compose up -d
```

If you installed manually, copy the updated integration and restart Home Assistant:

```bash
cp -R custom_components/hunch "$HA_CONFIG/custom_components/"
docker restart <homeassistant-container-name>
```

If you installed through HACS, update through HACS instead and restart Home Assistant.

## Troubleshooting

### Home Assistant cannot connect, but the server works on the Docker host

Check the Docker networking table. Do not use `localhost` from an ordinary bridge-network Home Assistant container. Also check the host firewall and confirm that port `8765` is published.

### The integration says the server is not ready

Run:

```bash
docker compose logs detector
docker compose ps
```

Confirm that `/app/download_model.py` completed successfully and that the `hunch-models` volume is attached. Wait for `/readyz` to return HTTP 200.

### The camera snapshot test fails

Open the snapshot URL from another device on the same network and verify that it returns an image rather than an HTML login page. Check the channel number, authentication method, username, password, and TLS setting. The Home Assistant container must also be able to reach the camera's address.

### No human detections occur

- Temporarily disable motion filtering to separate camera/model issues from motion configuration.
- Check that the detection zone includes the expected area.
- Lower the changed-area or pixel threshold if small movements are ignored.
- Review the entity's confidence attribute and adjust the human-confidence threshold carefully.
- Test the server directly with a known image containing a person.

### Too many false positives

Increase the motion changed-area threshold, require two consecutive motion frames, reduce the zone, or raise the human-confidence threshold. Tune separately for daytime, nighttime, and IR footage.

## Development

The Python workspace uses uv. Install dependencies and the Git hook with:

```bash
uv sync --all-packages
uv run pre-commit install
```

Run all lint, type, syntax, and configuration checks with:

```bash
uv run pre-commit run --all-files
```
