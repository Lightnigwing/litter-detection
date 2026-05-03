from .settings import RoboDogConfig, Settings

# Hardware-Bridge nur laden wenn das robot-Extra installiert ist.
try:
    from .go2_bridge import Go2Bridge
    from .robodog_control.robo_dog_controller import RoboDogController
except ImportError:
    Go2Bridge = None
    RoboDogController = None
