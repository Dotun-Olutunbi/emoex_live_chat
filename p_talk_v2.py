"""
Module summary
---------------
This module bridges a LiveKit audio room with a SoftBank Robotics Pepper robot,
allowing a PC microphone to be published to LiveKit and remote agent audio from
LiveKit to be played through Pepper's speaker. It also tracks voice activity and
latency events via a LatencyTracker object to measure user/agent speaking
periods and latency between them.
"""
import asyncio
import pyaudio
from livekit import rtc
import numpy as np
import dotenv
import concurrent.futures
import qi
from latencytracker import LatencyTracker

# Configuration
PEPPER_IP = "169.254.243.28"  # Change this to your Pepper's IP
PEPPER_PORT = 9559
PEPPER_VOLUME = 60  # Volume level 0-100 (default: 80)

dotenv.load_dotenv(".env.livekit")
USER_TOKEN = dotenv.get_key(".env.livekit", "USER_TOKEN")
ROOM_NAME = dotenv.get_key(".env.livekit", "ROOM_NAME")
WS_URL = dotenv.get_key(".env.livekit", "LIVEKIT_URL")

latency_tracker = LatencyTracker()

# Global Pepper connection
pepper_session = None
pepper_audio_device = None

def connect_to_pepper():
    """Connect to Pepper robot and return audio device service."""
    global pepper_session, pepper_audio_device
    try:
        print(f"Connecting to Pepper at {PEPPER_IP}:{PEPPER_PORT}...")
        pepper_session = qi.Session()
        pepper_session.connect(f"tcp://{PEPPER_IP}:{PEPPER_PORT}")
        pepper_audio_device = pepper_session.service("ALAudioDevice")
        
        # Set Pepper's volume
        try:
            pepper_audio_device.setOutputVolume(PEPPER_VOLUME)
            print(f"✅ Connected to Pepper successfully! Volume set to {PEPPER_VOLUME}%")
        except Exception as e:
            print(f"✅ Connected to Pepper, but couldn't set volume: {e}")
        
        return pepper_audio_device
    except Exception as e:
        print(f"❌ Failed to connect to Pepper: {e}")
        return None

async def play_audio_track(track: rtc.RemoteAudioTrack):
    """Receive agent audio from LiveKit and stream to Pepper."""
    audio_stream = rtc.AudioStream(track)
    
    agent_was_speaking = False
    first_frame = True
    silence_frames = 0
    silence_threshold_frames = int(latency_tracker.silence_duration * 100)
    
    try:
        async for event in audio_stream:
            frame = event.frame
            
            if first_frame:
                print(f"\n[AUDIO CONFIG] {frame.sample_rate}Hz, {frame.num_channels}ch")
                first_frame = False
            
            audio_bytes = frame.data.tobytes()
            
            if len(audio_bytes) > 0:
                # Calculate RMS for speech detection
                audio_array = np.frombuffer(audio_bytes, np.int16)
                mean_square = np.mean(audio_array.astype(np.float64)**2)
                
                if not np.isnan(mean_square) and mean_square >= 0:
                    rms = int(np.sqrt(mean_square))
                    if rms > 100:
                        print(f"[Agent speaking: RMS {rms}]", end=' ', flush=True)
                else:
                    rms = 0
                
                # Detect when agent starts/stops speaking
                is_speaking = rms > latency_tracker.agent_silence_threshold
                
                if is_speaking:
                    silence_frames = 0
                    if not agent_was_speaking:
                        latency_tracker.agent_started_responding()
                        agent_was_speaking = True
                else:
                    if agent_was_speaking:
                        silence_frames += 1
                        if silence_frames >= silence_threshold_frames:
                            latency_tracker.agent_stopped_responding()
                            agent_was_speaking = False
                            silence_frames = 0
                
                # Convert to Pepper format and send
                if pepper_audio_device:
                    # Convert mono to stereo by duplicating channels
                    if frame.num_channels == 1:
                        mono_array = np.frombuffer(audio_bytes, dtype=np.int16)
                        stereo_array = np.repeat(mono_array, 2)
                        stereo_bytes = stereo_array.tobytes()
                    else:
                        # Already stereo
                        stereo_bytes = audio_bytes
                    
                    # Resample if needed (Pepper expects 48kHz)
                    if frame.sample_rate != 48000:
                        print(f"⚠️  Warning: Sample rate is {frame.sample_rate}Hz, Pepper expects 48000Hz")
                    
                    # Send to Pepper
                    nbOfFrames = len(stereo_bytes) // 4  # 4 bytes per stereo frame (2 channels * 2 bytes)
                    try:
                        pepper_audio_device.sendRemoteBufferToOutput(nbOfFrames, bytes(stereo_bytes))
                    except Exception as e:
                        print(f"\n❌ Error sending audio to Pepper: {e}")
    
    except Exception as e:
        print(f"\n❌ Error in audio playback: {e}")

async def publish_microphone(local: rtc.LocalParticipant):
    """Publish PC microphone to LiveKit."""
    source = rtc.AudioSource(48000, 1)  # 48 kHz, mono
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)

    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    await local.publish_track(track, options)

    asyncio.create_task(capture_microphone(source))

async def capture_microphone(source: rtc.AudioSource):
    """Read PC microphone frames and push them to LiveKit."""
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=48000,
        input=True,
        frames_per_buffer=480)  # 10 ms @ 48 kHz
    
    user_was_speaking = False
    silence_frames = 0
    silence_threshold_frames = int(latency_tracker.silence_duration * 100)
    noise_gate_threshold = 80
    
    try:
        while True:
            data = stream.read(480, exception_on_overflow=False)
            frame = np.frombuffer(data, dtype=np.int16)
            
            # Calculate RMS for visual feedback
            rms = int(np.sqrt(np.mean(np.abs(frame.astype(np.float64))**2)))
            
            # Apply noise gate
            if rms < noise_gate_threshold:
                frame = np.zeros(480, dtype=np.int16)
                rms = 0
            
            if rms > 50:
                bar_length = min(30, rms // 100)
                bar = "█" * bar_length
                print(f"\r{bar:<30} {rms:4d}", end='', flush=True)
            
            is_speaking = rms > latency_tracker.user_silence_threshold
            
            if is_speaking:
                silence_frames = 0
                if not user_was_speaking:
                    latency_tracker.user_started_speaking()
                    user_was_speaking = True
            else:
                if user_was_speaking:
                    silence_frames += 1
                    if silence_frames >= silence_threshold_frames:
                        latency_tracker.user_stopped_speaking()
                        user_was_speaking = False
                        silence_frames = 0

            await source.capture_frame(rtc.AudioFrame(
                data=frame.tobytes(),
                sample_rate=48000,
                samples_per_channel=480,
                num_channels=1))
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


async def main() -> None:
    # Connect to Pepper first
    if not connect_to_pepper():
        print("⚠️  Continuing without Pepper connection (audio will be lost)")
    
    # Setup LiveKit room
    room = rtc.Room()
    agent_ready = asyncio.Event()
    agent_left = asyncio.Event()
    agent_identity = None

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        nonlocal agent_identity
        print(f"\n✅ Subscribed to {participant.identity}'s track")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"🤖 Agent audio connected: {participant.identity}")
            agent_identity = participant.identity
            agent_ready.set()  # Signal that agent is ready!
            asyncio.create_task(play_audio_track(track))

    @room.on("participant_connected")
    def on_participant_connected(participant):
        print(f"\n👤 {participant.identity} joined the room")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        print(f"\n👋 {participant.identity} left the room")
        # Check if this is the agent
        if participant.identity == agent_identity or len(room.remote_participants) == 0:
            print(f"\n❌ AGENT LEFT THE ROOM - Exiting...")
            agent_left.set()  # Signal to quit
    
    print("\nConnecting to LiveKit...")
    await room.connect(WS_URL, USER_TOKEN)
    print(f"✅ Connected to: {ROOM_NAME}")
    print(f"🔒 Room SID: {await room.sid}")
    
    # Publish microphone first
    await publish_microphone(room.local_participant)
    
    # List current participants
    all_ids = [room.local_participant.identity] + list(room.remote_participants.keys())
    print(f"\n👥 Current participants: {all_ids}")
    
    # Check if agent is already present
    if len(room.remote_participants) > 0:
        print("✅ Agent already in room!")
        agent_identity = list(room.remote_participants.keys())[0]
        agent_ready.set()
    else:
        print("\n⏳ Waiting for agent to join...")
        print("   (Script will wait indefinitely until agent connects)")
    
    # Wait indefinitely for agent (no timeout)
    await agent_ready.wait()
    print("✅ Agent is ready!\n")
    
    print("=" * 60)
    print("🎙️  VOICE LATENCY TRACKER (Pepper Output)")
    print("=" * 60)
    print("Speak into your PC mic. Agent will respond through Pepper.")
    print("Press Ctrl+C to exit and see final statistics.\n")
    
    try:
        # Wait for either KeyboardInterrupt or agent leaving
        await agent_left.wait()
        # If we get here, agent left
        print("\nAgent disconnected - shutting down...")
    except KeyboardInterrupt:
        print("\nInterrupted by user. Leaving...")
    finally:
        print("\n\nFinal Latency Statistics:")
        print("="*60)
        stats = latency_tracker.get_stats()
        if isinstance(stats, dict):
            print(f"  Average latency: {stats['average_ms']:.0f}ms")
            print(f"  Min latency: {stats['min_ms']:.0f}ms")
            print(f"  Max latency: {stats['max_ms']:.0f}ms")
            print(f"  Measurements: {stats['count']}")
        else:
            print("  No meaningful latency measurements recorded.")
            print(f"  {stats}")
        print("="*60 + "\n")
        
        await room.disconnect()
        if pepper_session:
            pepper_session.close()

if __name__ == "__main__":
    asyncio.run(main())