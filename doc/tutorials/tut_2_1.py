import time
import azrael.startup

# Start the Azrael stack.
az = azrael.startup.AzraelStack()
az.start()

# Wait until the user presses <ctrl-c>.
try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    pass

# Terminate the stack.
az.stop()
