"""Alternative music -> image models, each built on one mathematical law (see docs/MODELS.md)."""
from .chladni import ChladniPlate
from .grayscott import GrayScott
from .julia import JuliaZoom
from .kepler import KeplerSystem
from .lorenz import LorenzFlight

MODELS = {m.key: m for m in (LorenzFlight, JuliaZoom, KeplerSystem, GrayScott, ChladniPlate)}
