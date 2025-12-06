EmoEx Live Chat - Voice Latency Tracking

A set of Python scripts for bridging LiveKit audio rooms with microphone input, featuring real-time voice activity detection and latency measurement.

## Overview

This project provides two main applications for real-time voice communication:

1. c_talk.py - (computer_talk) Basic LiveKit client with PC microphone/speaker I/O
2. p_talk_v2.py - (pepper_talk) An advanced version connects Emoex with  Pepper robot integration
3. make_env.py - Utility script for generating LiveKit credentials from EmoEx AI

## Features

- Real-time microphone capture and playback via LiveKit
- Voice activity detection (VAD) for user and agent speech
- Automatic latency measurement between user and agent speech
- Pepper robot audio support (p_talk_v2.py)
- RMS-based noise gate and volume visualization
- Statistical tracking of latency measurements

## Requirements

### Python Packages
livekit
pyaudio
numpy
python-dotenv
requests

### Additional Requirements (for p_talk_v2.py)
- Pepper robot connectivity
- `qi` SDK for Pepper robot communication

## Installation

1. Clone or download this repository
2. Install required packages:

   pip install livekit pyaudio numpy python-dotenv requests

3. Set up environment variables in `.env`:
   
   EMOEX_EMAIL=your_email@example.com
   EMOEX_PASSWORD=your_password
   EMOEX_PRODUCT_ID=your_product_id
   FIREBASE_API_KEY=your_firebase_key
   FORCE_REFRESH=true

## Usage

### 1. Generate LiveKit Credentials

bash cmd:
    python make_env.py

This script:
- Authenticates with Firebase using EMOEX credentials
- Requests a LiveKit room token from the EmoEx API
- Extracts the thread ID from the JWT token
- Saves credentials to `.env.livekit`

Output: Creates `.env.livekit` file with:
- `USER_TOKEN` - LiveKit authentication token
- `ROOM_NAME` - Room identifier
- `LIVEKIT_URL` - WebSocket URL to LiveKit server
- `LAST_UPDATED` - Timestamp of last update

### 2. Run Emoex-PC Client (c_talk.py)

bash cmd: 
    python c_talk.py


Features:
- Connects to LiveKit room
- Publishes PC microphone audio
- Plays agent audio through PC speakers
- Displays real-time RMS levels and agent speech detection
- Measures latency between user speech and agent response
- Shows final statistics on exit (Ctrl+C)

Output:
Connecting to LiveKit...
 - Connected to: room_name
 - Room SID: abcd1234efgh5678
 - VOICE LATENCY TRACKER
 - Speak into your mic. Latency will be calculated.

Final Latency Statistics:
==============================================================
  Average latency: 1250ms
  Min latency: 800ms
  Max latency: 1850ms
  Measurements: 5
==============================================================


### 3. Run Emoex-Pepper Client (p_talk_v2.py | pepper_talk)

bash cmd:
    python p_talk_v2.py

**Requirements:**
- Pepper robot on network at `169.254.243.28` (an example)

**Configuration:**
Remember to edit the robot's IP (p_talk_v2.py) to adjust:

PEPPER_IP = "169.254.243.28"      # Pepper robot IP address
PEPPER_PORT = 9559                 # Pepper XML-RPC port
PEPPER_VOLUME = 60                 # Volume level 0-100

**Features of p_talk_v2.py:**
- All c_talk.py features
- Agent audio routed to Pepper's speakers
- Automatic mono-to-stereo conversion if needed
- Sample rate validation
- Better handling of Pepper's network disconnection

## Configuration

### Audio Settings
- **Sample Rate:** 48 kHz
- **Channels:** 1 (mono for input), stereo conversion for Pepper
- **Frame Size:** 480 samples (10ms @ 48kHz)
- **Format:** 16-bit PCM

### Voice Activity Detection
Adjust in `LatencyTracker` class (imported from latencytracker.py):
- `user_silence_threshold` - RMS threshold for user speech detection
- `agent_silence_threshold` - RMS threshold for agent speech detection
- `silence_duration` - Time (seconds) of silence before marking speech end
- `noise_gate_threshold` - Minimum RMS to avoid ambient noise

**Default noise gate:** 80 RMS (suppresses background noise below this level)

## Understanding the Output

### Real-time Display
```
█████████░░░░░░░░░░░░░░░░░░░░  1250
```
- Vertical bar graph showing microphone volume
- RMS value (0-32767 for 16-bit audio)

### Agent Speech Detection
```
[Agent speaking: RMS 450] [Agent speaking: RMS 480]
```
- Printed when agent RMS exceeds threshold
- Helps visualize speech patterns

### Latency Measurement
The script measures:
1. **User speech start** - When user RMS exceeds threshold
2. **Agent response start** - When agent RMS exceeds threshold
3. **Latency** = Agent start time - User start time
4. **Agent speech end** - After sustained silence period

## Troubleshooting

### No audio input/output
- Check `pyaudio` installation
- Verify microphone is connected and not muted
- Check volume settings on your PC

### LiveKit connection fails
- Verify `.env.livekit` file exists and contains valid tokens
- Check internet connection
- Run `make_env.py` again to refresh credentials
- Check LiveKit URL and token format

### Pepper audio not working
- Verify Pepper IP address is correct (`ping 169.254.243.28`)
- Check Pepper is powered on and XML-RPC service is running
- Verify volume setting (0-100)

### High latency measurements
- Normal for remote agents: 500ms-2000ms typical
- Check internet connection stability
- Verify audio frame sizes aren't causing delays

## Design/Architecture

### LatencyTracker
Tracks timing events:
- `user_started_speaking()` - Records when user begins speech
- `user_stopped_speaking()` - Records when user finishes
- `agent_started_responding()` - Records when agent begins response
- `agent_stopped_responding()` - Records when agent finishes
- `get_stats()` - Returns latency statistics (min, max, average, count)

### Audio Pipeline
```
Microphone → PyAudio → AudioSource → LiveKit Room → Remote Agent
                                          ↓
                                    Agent Audio Stream
                                          ↓
                            AudioStream → PyAudio/Pepper Speaker
```

## Environment Variables

### Required in `.env`
- `EMOEX_EMAIL` - EmoEx account email
- `EMOEX_PASSWORD` - EmoEx account password
- `EMOEX_PRODUCT_ID` - Product ID for your room
- `FIREBASE_API_KEY` - Firebase authentication key

### Optional
- `FORCE_REFRESH` - Force token refresh (default: "true")

### Generated in `.env.livekit` (by make_env.py)
- `USER_TOKEN` - LiveKit JWT token
- `ROOM_NAME` - Room name
- `LIVEKIT_URL` - WebSocket URL
- `LAST_UPDATED` - Timestamp

## Notes

- Tokens expire after ~1 hour (configurable by server)
- Run `make_env.py` to refresh tokens if needed

### Audio Frame Processing (Asynchronous)
Audio frames are processed asynchronously to minimize latency:
- PyAudio reads frames in a non-blocking manner from the microphone
- Each frame is independently pushed to LiveKit without waiting for previous frames
- Live remote audio is received and played without buffering delays
- Threading/async patterns prevent the UI from blocking during I/O operations
- Result: Typically 100-300ms lower latency compared to synchronous processing

**Technical implementation:**
- `await source.capture_frame()` sends microphone data to LiveKit without blocking
- `async for event in audio_stream:` receives agent audio asynchronously
- `asyncio.create_task()` spawns concurrent tasks for mic capture and audio playback
- Concurrent executors handle blocking PyAudio operations in background threads

### Voice Activity Detection (RMS Thresholding)
Voice activity detection uses simple RMS (Root Mean Square) thresholding instead of machine learning:

**How it works:**
- RMS measures the average energy/loudness of an audio frame (values 0-32767 for 16-bit audio)
- If RMS exceeds a threshold → speech detected
- If RMS stays below threshold for ~1 second → speech ended
- Noise gate further suppresses background noise below 80 RMS

**Why RMS thresholding instead of ML?**
- ✅ Low CPU overhead - runs efficiently on any hardware
- ✅ Real-time processing - no model loading or inference delays
- ✅ No network/cloud dependency - works offline
- ✅ Deterministic behavior - predictable and debuggable
- ❌ Less accurate than ML-based VAD - may miss soft speech or be triggered by loud noise

**Example thresholds (configurable):**
```
Silence (0-50 RMS)         → Not speaking
Speech (100-500 RMS)       → Speaking
Loud speech (500+ RMS)     → Strong speech signal
Noise gate threshold (80)  → Background noise suppression
```

You can tune these in `latencytracker.py` if needed for your environment.

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| livekit | Latest | WebRTC audio streaming |
| pyaudio | Latest | Local audio I/O |
| numpy | Latest |For audio frame processing |
| python-dotenv | Latest | For environment variable loading |
| requests | Latest | HTTP API calls |
| qi | Latest | Pepper robot SDK (for p_talk_v2.py only) |
