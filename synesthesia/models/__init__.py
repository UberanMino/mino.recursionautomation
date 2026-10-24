"""Alternative music -> image models, each built on one mathematical law (see docs/MODELS.md)."""
from .chladni import ChladniPlate
from .fractal import FractalFlight
from .grayscott import GrayScott
from .julia import JuliaZoom
from .kepler import KeplerSystem
from .lorenz import LorenzFlight
from .morph import MorphWorld

MODELS = {m.key: m for m in (LorenzFlight, JuliaZoom, KeplerSystem, GrayScott, ChladniPlate, FractalFlight,
                                 MorphWorld)}
