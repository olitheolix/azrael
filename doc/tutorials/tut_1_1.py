import time
import azrael.startup

# This will start the Azrael stack.
az = azrael.startup.AzraelStack()
az.start()

# Wait five seconds to see some screen output.
time.sleep(5)

# Terminate the Azrael.
az.stop()
