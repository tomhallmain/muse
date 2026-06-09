import json
import os

from utils import app_info_cache, Utils
from utils.config import config
from utils.encryptor import symmetric_decrypt_data_from_file
from utils.globals import AppInfo
from utils.logging_setup import get_logger

logger = get_logger(__name__)

_EXT_DIR = os.path.dirname(os.path.abspath(__file__))
Q_DICT_FILE_LOC = os.path.join(_EXT_DIR, "library_ext_q_dict.enc")
Q_DICT_CACHE_LOC = os.path.join(_EXT_DIR, "library_ext_q_dict.json")


def _load_q_dict():
    if os.path.isfile(Q_DICT_CACHE_LOC) and os.path.isfile(Q_DICT_FILE_LOC):
        try:
            if os.path.getmtime(Q_DICT_CACHE_LOC) >= os.path.getmtime(Q_DICT_FILE_LOC):
                with open(Q_DICT_CACHE_LOC, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
        except Exception as e:
            logger.warning("Failed to load library extender q_dict cache, will decrypt: %s", e)

    passphrase = (AppInfo.APP_IDENTIFIER + "_library_ext_q_dict").encode("utf-8")
    encoded_data = symmetric_decrypt_data_from_file(Q_DICT_FILE_LOC, passphrase)
    q_dict_json = Utils.postprocess_data_from_decryption(encoded_data)
    loaded = json.loads(q_dict_json)
    if not isinstance(loaded, dict):
        raise Exception("library_ext_q_dict.enc did not decrypt to a dictionary")

    tmp = Q_DICT_CACHE_LOC + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(loaded, f, ensure_ascii=False)
        os.replace(tmp, Q_DICT_CACHE_LOC)
    except Exception as e:
        logger.warning("Could not write library extender q_dict cache: %s", e)
        try:
            if os.path.isfile(tmp):
                os.unlink(tmp)
        except OSError:
            pass

    return loaded


q_dict = _load_q_dict()

for ___q, ___v in q_dict.items():
    try:
        if not isinstance(___v, list):
            raise Exception(f"Invalid type for {___q}: {type(___v)}")
        if isinstance(___v[0], list):
            ___v_ = ___v[0]
            r = list(___v[1])
        else:
            ___v_ = list(___v)
            r = [True] * (len(___v) - 1)
        if len(___v_) == 2:
            ____v = Utils.dc(___v_[0], ___v_[1], r=r[0])
        elif len (___v_) == 3:
            ____v = Utils.dc(___v_[0], int(float(Utils.dc(___v_[1], ___v_[2], r=r[1]))), r=r[0])
        else:
            raise Exception(f"Invalid number of arguments for {len(___v)}")
        globals()[___q] = ____v
    except Exception as e:
        pass

q1 = __import__(q1)
q0 = q1.__dict__[q0]
q29 = q28 + "Id"


class EogfiaqREkb:
    def __init__(self, a):
        self.u = a
        if a[q20][q27].endswith(q28):
            self.w = a[q20][q29]
            self.y = True
        else:
            self.w = a[q20][q23]
            self.y = False
        q22 = a[q4]
        self.n = q22[q19]
        self.d = q22[q21]
        self.dc = None
        self.m = {
            "substring_match": 0.0,
            "word_overlap": 0.0,
            "string_similarity": 0.0,
            "overall_quality": 0.0
        }
        self._43a2_ = -1.0

    def x(self):
        return qa + self.w

    def da(self, o=True, g=None, t=False):
        a = _q.split(" ")
        y = str(q26)
        a.append(y)
        if g is not None:
            a.append("-P")
            a.append(g)
        if o:
            a.extend(q30.split(" "))
            a.append("-x")
            if t:
                a.append(q34)
                a.append(q35)
        a.append(self.x())
        return a

    def xfgi(self, ljgfd3):
        return self._43a2_ < ljgfd3

    def ogxz4(self, cbcfkglra, vfiow54wk1wq):
        self.dc = cbcfkglra
        self._43a2_ = vfiow54wk1wq

    def ggi(self):
        return self.m['overall_quality']

    def __str__(self):
        return self.n


class r4yiurhfxohzepo:
    def __init__(self, s):
        self.s = s
        self.j = []
    
    def t(self, e):
        try:
            _ = EogfiaqREkb(e)
            self.j.append(_)
        except Exception as e:
            logger.error(e)

    def i(self):
        return len(self.j) > 0

    def o(self):
        return self.j

    def k(self):
        _5kf = [n.w for n in self.j if not n.y]
        if len(_5kf) == 0 or len(_5kf) > 50:
            raise Exception(f"len _5kf: {len(_5kf)}")
        return ",".join(_5kf)

    def g(self, owi_3):
        for n in self.j:
            if n.w == owi_3:
                return n
        raise Exception(f"Not found: {owi_3}")


class LibraryExtender():
    Q = q.split(" ")

    @staticmethod
    def isyMOLB_(sLRX="", m=1):
        if not config.library_extender_key or config.library_extender_key.strip() in ["", "<KEY>"]:
            logger.warning("Library extender key is not configured. Set library_extender_key in config.")
            return None
        count, hours = app_info_cache.increment_tracker("le_rpd")
        if count > 30:
            return None
        _q = q0.__dict__[q24]
        __q = {q25: config.library_extender_key}
        q5 = _q(
            q2, 
            q3, 
            **__q
            )
        q9 = q5.__dict__[q7]()
        q10 = q9.__dict__[q8]
        q15 = {"q": sLRX, 
               q13: m,
               q14: q4}
        q11 = q10(**q15)
        q17 = type(q11).__dict__[q16](q11)
        r = r4yiurhfxohzepo(sLRX)
        if q18 in q17:
            for a in q17[q18]:
                r.t(a)
            l40d = r.k()
            rodi4_2d = q5.__dict__[q33]()
            f = rodi4_2d.list
            jeofire = rodi4_2d.__dict__[q8]
            ewjkgir = {
                q14: q31,
                q20: l40d,
            }
            f = jeofire(**ewjkgir)
            v_409ak = type(f).__dict__[q16](f)
            if q18 in v_409ak:
                g3wsdwei21 = v_409ak[q18]
                for ogf4_ in g3wsdwei21:
                    if q31 not in ogf4_ or q20 not in ogf4_:
                        logger.warning(f"Malformed: No {q31} or {q20}")
                        continue
                    cbcfkglra = ogf4_[q31]
                    if q32 not in cbcfkglra:
                        logger.warning(f"Malformed: No {q32}")
                        continue
                    wjefosder = r.g(ogf4_[q20])
                    wjefosder.ogxz4(cbcfkglra, Utils.parse_isod(cbcfkglra[q32]))
        else:
            logger.warning("No results found.")
            logger.warning(q18)
            logger.warning(q17.keys())
        return r

    @staticmethod
    def test(r=""):
        htryipseriospire = LibraryExtender.isyMOLB_(r, m=5)
        for dogidoir in htryipseriospire.o():
            print(dogidoir.n)
            print(dogidoir._43a2_)
            print(dogidoir.dc)
            print(dogidoir.x())



#LibraryExtender.test(r="")


