from __future__ import annotations

from collections.abc import Callable

from .base import ProgrammeAdapter
from .birmingham import BirminghamAdapter
from .bristol import BristolAdapter
from .caltech import CaltechAdapter
from .cambridge import CambridgeAdapter
from .cuhk import CUHKAdapter
from .edinburgh import EdinburghAdapter
from .eth import ETHAdapter
from .glasgow import GlasgowAdapter
from .harvard import HarvardAdapter
from .hku import HKUAdapter
from .hkust import HKUSTAdapter
from .imperial import ImperialAdapter
from .kcl import KCLAdapter
from .manchester import ManchesterAdapter
from .melbourne import MelbourneAdapter
from .mit import MITAdapter
from .monash import MonashAdapter
from .ntu import NTUAdapter
from .nus import NUSAdapter
from .oxford import OxfordAdapter
from .peking import PekingAdapter
from .polyu import PolyUAdapter
from .southampton import SouthamptonAdapter
from .stanford import StanfordAdapter
from .sydney import SydneyAdapter
from .tsinghua import TsinghuaAdapter
from .tudelft import TUDelftAdapter
from .uq import UQAdapter

AdapterFactory = Callable[[], ProgrammeAdapter]

PROGRAMME_ADAPTERS: dict[str, AdapterFactory] = {
    "birmingham": BirminghamAdapter,
    "bristol": BristolAdapter,
    "caltech": CaltechAdapter,
    "cambridge": CambridgeAdapter,
    "cuhk": CUHKAdapter,
    "edinburgh": EdinburghAdapter,
    "eth": ETHAdapter,
    "glasgow": GlasgowAdapter,
    "harvard": HarvardAdapter,
    "hku": HKUAdapter,
    "hkust": HKUSTAdapter,
    "imperial": ImperialAdapter,
    "kcl": KCLAdapter,
    "melbourne": MelbourneAdapter,
    "manchester": ManchesterAdapter,
    "mit": MITAdapter,
    "monash": MonashAdapter,
    "ntu": NTUAdapter,
    "nus": NUSAdapter,
    "oxford": OxfordAdapter,
    "peking": PekingAdapter,
    "polyu": PolyUAdapter,
    "southampton": SouthamptonAdapter,
    "stanford": StanfordAdapter,
    "sydney": SydneyAdapter,
    "tsinghua": TsinghuaAdapter,
    "tudelft": TUDelftAdapter,
    "uq": UQAdapter,
}
