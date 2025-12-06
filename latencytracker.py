import time
from collections import deque

class LatencyTracker:
    """Track latency metrics for voice conversations."""
    
    def __init__(self):
        self.user_speaking_start = None
        self.user_speaking_end = None
        self.agent_response_start = None
        self.agent_response_end = None
        self.user_silence_threshold = 150  # User speech detection
        self.agent_silence_threshold = 200  # Agent speech detection (higher to avoid false positives)
        self.silence_duration = 1.0  # Longer silence before confirming "stopped"
        self.conversation_count = 0
        self.recent_latencies = deque(maxlen=10)  # Keep last 10 measurements
        
    def user_started_speaking(self):
        """Called when user starts speaking."""
        self.user_speaking_start = time.time()
        self.agent_response_start = None
        print(f"\n{'='*60}")
        print(f"[USER SPEAKING] Started at {time.strftime('%H:%M:%S')}")
                
    def user_stopped_speaking(self):
        """Called when user stops speaking."""
        self.user_speaking_end = time.time()
        if self.user_speaking_start:
            duration = self.user_speaking_end - self.user_speaking_start
            print(f"[LATENCY] User stopped speaking (spoke for {duration:.2f}s)")
        
    def agent_started_responding(self):
        """Called when agent starts responding."""
        self.agent_response_start = time.time()
        
        if self.user_speaking_end:
            # Time from user stopped speaking to agent started responding
            latency = self.agent_response_start - self.user_speaking_end
            self.recent_latencies.append(latency)
            
            avg_latency = sum(self.recent_latencies) / len(self.recent_latencies)
            
            print(f"\n[LATENCY MEASUREMENT]")
            print(f"  Response latency: {latency*1000:.0f}ms")
            print(f"  Average (last {len(self.recent_latencies)}): {avg_latency*1000:.0f}ms")
            print(f"  Min: {min(self.recent_latencies)*1000:.0f}ms")
            print(f"  Max: {max(self.recent_latencies)*1000:.0f}ms\n")
        
    def agent_stopped_responding(self):
        """Called when agent stops responding."""
        self.agent_response_end = time.time()
        if self.agent_response_start:
            duration = self.agent_response_end - self.agent_response_start
            print(f"[LATENCY] Agent finished responding (spoke for {duration:.2f}s)")
            print(f"{'='*60}\n")
            
    def get_stats(self):
        """Get latency statistics."""
        if not self.recent_latencies:
            return "No latency measurements yet"
        
        avg = sum(self.recent_latencies) / len(self.recent_latencies)
        return {
            'average_ms': avg * 1000,
            'min_ms': min(self.recent_latencies) * 1000,
            'max_ms': max(self.recent_latencies) * 1000,
            'count': len(self.recent_latencies)
            # 'total_turns': self.conversation_count
        }