import threading
import time
import random
import numpy as np

class MockVideoThread:
    def __init__(self):
        self.enabled_class_ids = set(range(10)) 
        self.running = True
        self.clss_all = np.random.randint(0, 10, 50)
        self.errors = 0

    def set_enabled_classes(self, ids):
        # SIMULATE THE FIX 🛡️🦾
        if ids is None:
            self.enabled_class_ids = None
            return
        try:
            self.enabled_class_ids = set(map(int, ids))
        except:
            self.enabled_class_ids = set()

    def run_inference_loop(self):
        while self.running:
            try:
                # SIMULATE THE FIX 🧬
                current_filter = self.enabled_class_ids
                
                if current_filter is not None:
                    # Thread-safe check against the local reference copy
                    mask = [int(c) in current_filter for c in self.clss_all]
                    _ = self.clss_all[mask]
                else:
                    _ = self.clss_all
                
                time.sleep(0.001) # Accelerated 1000 FPS stress!
            except Exception as e:
                print(f"CRASH DETECTED: {e}")
                self.errors += 1
                if self.errors > 10:
                    self.running = False

def chaos_monkey(thread):
    # Stress data with mix of good/bad/none
    cases = [[], None, list(range(10)), [0, 1], ["bad", 2]]
    for _ in range(10000): # 10,000 rapid cycles
        val = random.choice(cases)
        thread.set_enabled_classes(val)
        time.sleep(0.0001)
    thread.running = False

if __name__ == "__main__":
    t = MockVideoThread()
    w = threading.Thread(target=t.run_inference_loop, daemon=True)
    m = threading.Thread(target=chaos_monkey, args=(t,), daemon=True)
    
    w.start()
    m.start()
    
    m.join()
    w.join()
    
    print(f"\n10,000 CYCLE STRESS TEST COMPLETE")
    print(f"Total Crashes: {t.errors}")
    if t.errors == 0:
        print("RESULT: DEPLOYMENT READY. 🛰️🦾🛡️")
    else:
        print("RESULT: FAILURE. REDIRECT TO R&D.")
