import math
import re
import unittest
from dataclasses import replace
from xml.etree import ElementTree

from itm_model import Invoer
from pfd.bedrijfspunt import momentopname
from pfd.schema import OPSTELLINGEN, schema


def industrie(**wijzigingen):
    return replace(Invoer(net_aan=False, wp_aan=False, h2_warmteterugwinning=False, Q_ind=math.inf),
                   **wijzigingen)


class LivePfdTest(unittest.TestCase):
    def test_industrie_capaciteit_en_balansen(self):
        r, data = momentopname(industrie(), "industrie", (1.0,) * 8)
        self.assertAlmostEqual(r["Q_ind"] / 1000, 19.52, delta=0.02)
        self.assertAlmostEqual(r["COP2"], 3.53, delta=0.02)
        self.assertAlmostEqual(r["Q_L2"], 14000, delta=1e-6)
        self.assertAlmostEqual(r["Q_L2"] + r["W_K202"], r["Q_ind"])
        self.assertAlmostEqual(data["waarden"]["massa.verschil"]["getal"], 32)
        self.assertEqual(data["waarden"]["S9.kg_h"]["getal"], 0)

    def test_temperatuur_werkt_door_in_stofeigenschappen_en_rekenstappen(self):
        punt = (1.0,) * 8
        _, voor = momentopname(industrie(), "industrie", punt)
        _, na = momentopname(industrie(T_ind_aanvoer=100), "industrie", punt)
        v = na["waarden"]
        for sleutel in ("COP2", "I1.rho", "I1.m3_h"):
            self.assertNotEqual(voor["waarden"][sleutel]["getal"], v[sleutel]["getal"])
        self.assertEqual(v["wp202.Tc"]["getal"], 105)
        self.assertEqual(v["COP2"]["argumenten"], {"q": "wp202.q", "w": "wp202.w"})
        self.assertAlmostEqual(v["I1.kg_h"]["getal"] / 3600, v["I1.kg_s"]["getal"])
        self.assertAlmostEqual(v["I1.kg_h"]["getal"] / v["I1.rho"]["getal"], v["I1.m3_h"]["getal"])
        self.assertAlmostEqual(v["I1.m3_h"]["getal"] / 3600, v["I1.m3_s"]["getal"])
        with self.assertRaisesRegex(ValueError, "industrieretour"):
            momentopname(industrie(T_ind_retour=100), "industrie", punt)

    def test_deellast_en_uitgeschakelde_cyclus(self):
        i = industrie(n_units=1, belasting=25, Q_ind=0)
        r, data = momentopname(i, "industrie", (0.25,) + (0,) * 7)
        self.assertAlmostEqual(data["waarden"]["S9.kg_h"]["getal"], 13.5)
        self.assertAlmostEqual(r["Q_AK"], i.Q_ITM_EOL * 0.25)
        self.assertIsNone(data["waarden"]["COP2"]["getal"])
        self.assertEqual(data["waarden"]["R5.m3_s"]["getal"], 0)

    def test_stilstand_heeft_op_beide_bladen_nuldebiet(self):
        for opstelling in OPSTELLINGEN:
            with self.subTest(opstelling=opstelling):
                i = industrie() if opstelling == "industrie" else Invoer()
                r, data = momentopname(replace(i, n_units=0, belasting=0), opstelling, (0,) * 8)
                self.assertIsNone(r)
                self.assertIsNone(data["waarden"]["COP2"]["getal"])
                for toestand in data["stromen"].values():
                    for sleutel in ("kg_h", "kg_s", "m3_h", "m3_s"):
                        self.assertEqual(data["waarden"][toestand["waarden"][sleutel]]["getal"], 0)

    def test_drawio_poorten_en_herkomst_koppelen_aan_actuele_waarden(self):
        for opstelling in OPSTELLINGEN:
            with self.subTest(opstelling=opstelling):
                i = industrie() if opstelling == "industrie" else Invoer()
                r, data = momentopname(i, opstelling, (1.0,) * 8)
                if opstelling == "warmtenet":
                    self.assertEqual(r["Q_ind"], 2000)
                    self.assertGreater(r["Q_net"], 0)
                blad = schema(opstelling)
                cellen = {cel.get("id"): cel for cel in ElementTree.fromstring(blad["xml"]).findall("root/mxCell")}
                for id_, lijn in blad["leidingen"].items():
                    for rol, veld in (("bron", "source"), ("doel", "target")):
                        self.assertEqual(cellen[id_].get(veld), lijn[rol])
                        self.assertIn(lijn[rol], cellen)
                    if lijn["stroom"]:
                        self.assertIn(lijn["stroom"], data["stromen"])
                waarden = data["waarden"]
                for item in waarden.values():
                    self.assertEqual(set(re.findall(r"@(\w+)", item["formule"])), set(item["argumenten"]))
                    for verwijzing in item["argumenten"].values():
                        self.assertIn(verwijzing, waarden)
