from ..stdlib.pump import Pump
from . import _ureg


class KnauerPump(Pump):
    """
    A Knauer Azura Compact P2.1 pump

    Please see : https://www.knauer.net/Dokumente/pumps/azura/manuals/V6870%20_P2.1S_P4.1S_Instructions.pdf


    - `mac_address`: Mac address of the pump

    """

    metadata = {
        "author": [
            {
                "first_name": "Dario",
                "last_name": "Cambie",
                "email": "dario.cambie@mpikg.mpg.de",
                "institution": "Max Planck Institute of Colloids and interfaces",
                "github_username": "dcambie",
            }
        ],
        "stability": "beta",
        "supported": True,
    }

    def __init__(self, mac_address, name=None):
        super().__init__(name=name)
        self.rate = _ureg.parse_expression("0 ml/min")
        self.mac_address = mac_address

    def __enter__(self):
        from flowchem import KnauerPump
        self._pump = KnauerPump.from_mac(mac_address=self.mac_address)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._pump.stop_flow()
        del self._pump

    async def _set_flow(self, flow_rate):
        """
        Sets the target flow rate

        Args:
            flow_rate: a pint Quantity

        Returns: None

        """
        self._pump.set_flow(setpoint_in_ml_min=flow_rate.to(_ureg.ml / _ureg.min).magnitude)

    async def _update(self):
        await self._set_flow(self.rate)
