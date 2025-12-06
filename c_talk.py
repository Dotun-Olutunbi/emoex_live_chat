import asyncio
import pyaudio
from livekit import rtc
import numpy as np
import dotenv
import concurrent.futures
import time
from collections import deque
from latencytracker import LatencyTracker

dotenv.load_dotenv(".env.livekit")
USER_TOKEN = dotenv.get_key(".env.livekit", "USER_TOKEN")
ROOM_NAME = dotenv.get_key(".env.livekit", "ROOM_NAME")
WS_URL = dotenv.get_key(".env.livekit", "LIVEKIT_URL")

latency_tracker = LatencyTracker()

async def play_audio_track(track: rtc.RemoteAudioTrack):
    pa = pyaudio.PyAudio()
    audio_stream = rtc.AudioStream(track)
    loop = asyncio.get_running_loop()
    
    stream = None
    # frame_count = 0
    agent_was_speaking = False
    # silence_start = None
    first_frame = True
    silence_frames = 0
    silence_threshold_frames = int(latency_tracker.silence_duration * 100)  # ~100 frames/sec
    
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            async for event in audio_stream:
                frame = event.frame
                # frame_count += 1
                if first_frame:
                    # print(f"\n[DEBUG] Received first audio frame")
                    print(f"\n[First frameAUDIO CONFIG] {frame.sample_rate}Hz, {frame.num_channels}ch")
                    first_frame = False
                
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=frame.num_channels,
                        rate=frame.sample_rate,
                        output=True,
                        frames_per_buffer=frame.samples_per_channel
                    )
                    
                audio_bytes = frame.data.tobytes()
                # run the blocking write in a thread
                if len(audio_bytes) > 0:
                    audio_array = np.frombuffer(audio_bytes, np.int16)
                    mean_square = np.mean(audio_array.astype(np.float64)**2)
                    
                    
                    # rms = int(np.sqrt(mean_square)) if mean_square 0 else 0
                    if not np.isnan(mean_square) and mean_square >= 0:
                        rms = int(np.sqrt(mean_square))
                        # Only print when agent is speaking loudly
                        if rms > 100:
                            print(f"[Agent speaking: RMS {rms}]", end=' ', flush=True)
                    else:
                        rms = 0
                
                # Detect when agent starts/stops speaking
                    is_speaking = rms > latency_tracker.agent_silence_threshold
                    
                    if is_speaking:
                        silence_frames = 0
                        if not agent_was_speaking:
                            # Agent started speaking
                            latency_tracker.agent_started_responding()
                            agent_was_speaking = True
                    else:
                        if agent_was_speaking:
                            silence_frames += 1
                            if silence_frames >= silence_threshold_frames:
                                # Agent confirmed stopped speaking
                                latency_tracker.agent_stopped_responding()
                                agent_was_speaking = False
                                silence_frames = 0
                
                await loop.run_in_executor(pool, stream.write, frame.data.tobytes())
                 # Write directly without executor
                # stream.write(audio_bytes, exception_on_underflow=False)  # Added exception flag
            
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            pa.terminate()

async def publish_microphone(local: rtc.LocalParticipant):
    # Ask Windows for an audio track
    source = rtc.AudioSource(48000, 1)          # 48 kHz, mono
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)

    # Publish it to the room
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    await local.publish_track(track, options)

    # Start the capture loop (keeps the mic open)
    asyncio.create_task(capture_microphone(source))

async def capture_microphone(source: rtc.AudioSource):
    """Read microphone frames and push them into the source."""
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=48000,
        input=True,
        frames_per_buffer=480)          # 10 ms @ 48 kHz
    
    user_was_speaking = False
    silence_frames = 0
    silence_threshold_frames = int(latency_tracker.silence_duration * 100)
    
    noise_gate_threshold = 80  # RMS below this is always silence
    
    try:
        while True:
            data = stream.read(480, exception_on_overflow=False)
            frame = np.frombuffer(data, dtype=np.int16)
            
            # Calculate RMS for visual feedback
            rms = int(np.sqrt(np.mean(np.abs(frame.astype(np.float64))**2)))
            
            # Apply noise gate - send silence if below threshold
            if rms < noise_gate_threshold:
                # Send silence instead of ambient noise
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
                    # User started speaking
                    latency_tracker.user_started_speaking()
                    user_was_speaking = True
                
            else:
                if user_was_speaking:
                    silence_frames += 1
                if silence_frames >= silence_threshold_frames:
                    # Confirmed end of speech
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
    # The room object
    room = rtc.Room()
    agent_ready = asyncio.Event()

    # Define event handlers
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        print(f"\nSubscribed to {participant.identity}'s track")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"Agent connected: {participant.identity}...")
            asyncio.create_task(play_audio_track(track))

    @room.on("participant_connected")
    def on_participant_connected(participant):
        print(f"\n{participant.identity} connected")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        print(f"\n{participant.identity} disconnected")
        
    print("Connecting to LiveKit...")
    await room.connect(WS_URL, USER_TOKEN)
    print(f"✅ Connected to: {ROOM_NAME}")
    print(f"📍 Room SID: {await room.sid}") # SID = room's unique ID
    
    # Wait up to 15 seconds for agent
    try:
        await asyncio.wait_for(agent_ready.wait(), timeout=15.0)
        print("✅ Agent is ready!")
    except asyncio.TimeoutError:
        print("⚠️  Agent didn't join within 15s. Starting anyway...")
        
    print("\n" + "="*60)
    print("🎙️  VOICE LATENCY TRACKER")
    print("="*60)
    print("Speak into your mic. Latency will be calculated.")
    print("Press Ctrl+C to exit and see final statistics.\n")
    
    await publish_microphone(room.local_participant)

    all_ids = [room.local_participant.identity] + list(room.remote_participants.keys())
    print(f"Participants: {all_ids}")
    
    await publish_microphone(room.local_participant)
    
    try:
        await asyncio.Event().wait()  # Keep running until interrupted
    except KeyboardInterrupt:
        print("\nInterrupted. Leaving...")
        print("\n\nFinal Latency Statistics:")
        print("="*60)
        stats = latency_tracker.get_stats()
        if isinstance(stats, dict):
            # print(f"  Total Conversations: {stats['total_turns']}")
            print(f"  Average latency: {stats['average_ms']:.0f}ms")
            print(f"  Min latency: {stats['min_ms']:.0f}ms")
            print(f"  Max latency: {stats['max_ms']:.0f}ms")
            print(f"  Measurements: {stats['count']}")
        else:
            print("  No meaningful latency measurements recorded.")
            print(f"  {stats}")
        print("="*60 + "\n")
    finally:
        await room.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
    
    
    
#The agents statements are incomplete, they stop abruptly and starts a new sentence. Fix it