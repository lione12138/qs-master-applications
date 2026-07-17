from __future__ import annotations

from collections.abc import Callable

from .anu import ANUAdapter
from .auckland import AucklandAdapter
from .base import ProgrammeAdapter
from .berkeley import BerkeleyAdapter
from .birmingham import BirminghamAdapter
from .bristol import BristolAdapter
from .brown import BrownAdapter
from .caltech import CaltechAdapter
from .cambridge import CambridgeAdapter
from .cmu import CMUAdapter
from .columbia import ColumbiaAdapter
from .cornell import CornellAdapter
from .cuhk import CUHKAdapter
from .edinburgh import EdinburghAdapter
from .epfl import EPFLAdapter
from .eth import ETHAdapter
from .fudan import FudanAdapter
from .glasgow import GlasgowAdapter
from .harvard import HarvardAdapter
from .hku import HKUAdapter
from .hkust import HKUSTAdapter
from .imperial import ImperialAdapter
from .ip_paris import IPParisAdapter
from .jhu import JHUAdapter
from .kaist import KAISTAdapter
from .kcl import KCLAdapter
from .kfupm import KFUPMAdapter
from .korea import KoreaUniversityAdapter
from .ku_leuven import KULeuvenAdapter
from .kyoto import KyotoAdapter
from .lmu import LMUAdapter
from .lse import LSEAdapter
from .manchester import ManchesterAdapter
from .mcgill import McGillAdapter
from .melbourne import MelbourneAdapter
from .mit import MITAdapter
from .monash import MonashAdapter
from .northwestern import NorthwesternAdapter
from .ntu import NTUAdapter
from .ntu_tw import NTUTaiwanAdapter
from .nus import NUSAdapter
from .nyu import NYUAdapter
from .oxford import OxfordAdapter
from .peking import PekingAdapter
from .polyu import PolyUAdapter
from .princeton import PrincetonAdapter
from .psl import PSLAdapter
from .sjtu import SJTUAdapter
from .snu import SNUAdapter
from .southampton import SouthamptonAdapter
from .stanford import StanfordAdapter
from .sydney import SydneyAdapter
from .toronto import TorontoAdapter
from .tsinghua import TsinghuaAdapter
from .tudelft import TUDelftAdapter
from .tum import TUMAdapter
from .ubc import UBCAdapter
from .uchicago import UChicagoAdapter
from .ucl import UCLAdapter
from .ucla import UCLAAdapter
from .um import UMAdapter
from .umich import UMichAdapter
from .unsw import UNSWAdapter
from .upenn import UpennAdapter
from .uq import UQAdapter
from .utokyo import UTokyoAdapter
from .uva import UvAAdapter
from .yale import YaleAdapter
from .yonsei import YonseiAdapter
from .zju import ZJUAdapter

AdapterFactory = Callable[[], ProgrammeAdapter]

PROGRAMME_ADAPTERS: dict[str, AdapterFactory] = {
    "anu": ANUAdapter,
    "auckland": AucklandAdapter,
    "berkeley": BerkeleyAdapter,
    "birmingham": BirminghamAdapter,
    "bristol": BristolAdapter,
    "brown": BrownAdapter,
    "caltech": CaltechAdapter,
    "cambridge": CambridgeAdapter,
    "columbia": ColumbiaAdapter,
    "cmu": CMUAdapter,
    "cornell": CornellAdapter,
    "cuhk": CUHKAdapter,
    "edinburgh": EdinburghAdapter,
    "epfl": EPFLAdapter,
    "eth": ETHAdapter,
    "fudan": FudanAdapter,
    "glasgow": GlasgowAdapter,
    "harvard": HarvardAdapter,
    "hku": HKUAdapter,
    "hkust": HKUSTAdapter,
    "imperial": ImperialAdapter,
    "ip-paris": IPParisAdapter,
    "jhu": JHUAdapter,
    "kaist": KAISTAdapter,
    "kcl": KCLAdapter,
    "kfupm": KFUPMAdapter,
    "korea": KoreaUniversityAdapter,
    "ku-leuven": KULeuvenAdapter,
    "kyoto": KyotoAdapter,
    "lmu": LMUAdapter,
    "lse": LSEAdapter,
    "melbourne": MelbourneAdapter,
    "manchester": ManchesterAdapter,
    "mcgill": McGillAdapter,
    "mit": MITAdapter,
    "monash": MonashAdapter,
    "ntu": NTUAdapter,
    "ntu-taiwan": NTUTaiwanAdapter,
    "nus": NUSAdapter,
    "northwestern": NorthwesternAdapter,
    "oxford": OxfordAdapter,
    "nyu": NYUAdapter,
    "peking": PekingAdapter,
    "polyu": PolyUAdapter,
    "princeton": PrincetonAdapter,
    "psl": PSLAdapter,
    "sjtu": SJTUAdapter,
    "snu": SNUAdapter,
    "southampton": SouthamptonAdapter,
    "stanford": StanfordAdapter,
    "sydney": SydneyAdapter,
    "tsinghua": TsinghuaAdapter,
    "toronto": TorontoAdapter,
    "tudelft": TUDelftAdapter,
    "tum": TUMAdapter,
    "um": UMAdapter,
    "ubc": UBCAdapter,
    "ucla": UCLAAdapter,
    "ucl": UCLAdapter,
    "uchicago": UChicagoAdapter,
    "umich": UMichAdapter,
    "unsw": UNSWAdapter,
    "uq": UQAdapter,
    "upenn": UpennAdapter,
    "utokyo": UTokyoAdapter,
    "uva": UvAAdapter,
    "yale": YaleAdapter,
    "yonsei": YonseiAdapter,
    "zju": ZJUAdapter,
}
