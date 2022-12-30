# importing module
import logging

# Create and configure logger
logging.basicConfig(
    filename=f"program logs.log",
    format="%(asctime)s - %(levelname)s - %(message)s args:%(args)s - %(pathname)s line: %(lineno)d\n",
    filemode="a",
)

# Creating an object
logger = logging.getLogger(__name__)

# Setting the threshold of logger to DEBUG
logger.setLevel(logging.DEBUG)

# Test messages
# logger.debug("Harmless debug Message", {1: 1})
# logger.info("Just an information")
# logger.warning("Its a Warning")
# logger.error("Did you try to divide by zero")
# logger.critical("Internet is down")
