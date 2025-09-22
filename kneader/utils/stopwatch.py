import time

class Stopwatch:
    def __init__(self):
        self.start_time = None
        self.elapsed_time = 0
        self.is_running = False

    def start(self):
        if not self.is_running:
            self.start_time = time.time()  # Record the current time when starting
            self.is_running = True
            #print("Stopwatch started.")
        else:
            pass
            #print("Stopwatch is already running.")

    def stop(self):
        if self.is_running:
            self.elapsed_time += time.time() - self.start_time  # Add only the running time
            self.is_running = False
            #print("Stopwatch stopped.")
        else:
            pass
            #print("Stopwatch is not running.")

    def reset(self):
        self.start_time = None
        self.elapsed_time = 0
        self.is_running = False
        #print("Stopwatch reset.")

    def get_elapsed_time(self):
        if self.is_running:
            # If running, add the current running time to the elapsed time
            total_elapsed = self.elapsed_time + (time.time() - self.start_time)
        else:
            # If stopped, only use the elapsed time
            total_elapsed = self.elapsed_time

        # Convert to hours, minutes, and seconds
        hours = int(total_elapsed // 3600)
        minutes = int((total_elapsed % 3600) // 60)
        seconds = int(total_elapsed % 60)
        return f"{hours:02}.{minutes:02}.{seconds:02}"

    def display_time(self):
        print(f"Elapsed Time: {self.get_elapsed_time()}")

