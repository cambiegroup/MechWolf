import mechwolf as mw
import os

os.environ["PATH"]  += os.pathsep + r"C:\UserApps\PyMOL.app\envs\MechWolf\Library\bin\graphviz"

# Two feeds
substrate = mw.Vessel("p-iodobenzotrifluoride 1M in DMAc", name="substrate")
sulfinate = mw.Vessel("p-toluensulfinate 2M in DMAc", name="sulfinate")

# Two pumps
substrate_pump = mw.KnauerPump(name="substrate_pump", mac_address='00:20:4a:f9:00:74')
sulfinate_pump = mw.KnauerPump(name="sulfinate_pump", mac_address='00:80:a3:9b:bf:6a')


# Mixer
mixer = mw.TMixer(name='mixer')

# Reactor
reactor = mw.Vessel("Photoreactor", name="reactor")

# Analytics
# nmr = mw.Spinsolve(name="Proton")

A = mw.Apparatus("Synthesizer")

def tefzel(len):
    return mw.Tube(length=len, ID="1.0 mm", OD="1/16 in", material="Tefzel")

# TUBING

# bottle to pump
A.add(substrate, substrate_pump, tefzel("20 cm"))
A.add(sulfinate, sulfinate_pump, tefzel("20 cm"))

# Pump to mixer
A.add([substrate_pump, sulfinate_pump] , mixer, tefzel("20 cm"))

# Mixer to reactor
A.add(mixer, reactor, tefzel("20 cm"))

A.describe()
# A.visualize(graph_attr=dict(splines="ortho", nodesep="0.75"), label_tubes=False)

P = mw.Protocol(A)

from datetime import timedelta

rinse_duration = timedelta(seconds=2)
start = timedelta(seconds=0)

# P.add([substrate_pump, sulfinate_pump], start=start, duration=rinse_duration, setting="dmf")
P.add([substrate_pump, sulfinate_pump], start=start, duration=rinse_duration, rate="1 mL/min")

P.visualize()
print(P)

E = P.execute(dry_run=False)

#%%

#Visualize the experiment with live updating
E.visualize()

#%%

#Inspect the protocol steps that ran successfully.
E.protocol.json()
