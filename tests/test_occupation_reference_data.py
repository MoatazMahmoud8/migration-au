import json
import unittest
from pathlib import Path


PUBLIC = Path(__file__).parents[1] / "public"


class OccupationReferenceDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fee_data = json.loads((PUBLIC / "visa-fees.json").read_text(encoding="utf-8"))
        occupation_data = json.loads((PUBLIC / "skilled-occupations.json").read_text(encoding="utf-8"))
        cls.fees = {item["subclass"]: item for item in fee_data["items"]}
        cls.occupations = {item["anzsco"]: item for item in occupation_data["items"]}

    def test_2026_27_skilled_visa_fees(self):
        expected = {
            "189": "AUD $6,140",
            "190": "AUD $6,140",
            "491": "AUD $6,140",
            "482": "AUD $4,015",
            "494": "AUD $6,140",
            "186": "AUD $6,140",
        }

        self.assertEqual(
            {subclass: self.fees[subclass]["fee"] for subclass in expected},
            expected,
        )
        for subclass in ("189", "190", "491", "186"):
            self.assertIn("+$3,070 per adult", self.fees[subclass]["note"])

    def test_nursing_and_pharmacy_authorities(self):
        nurses = [
            item for code, item in self.occupations.items()
            if code.startswith(("2541", "2544"))
        ]
        pharmacists = [
            item for code, item in self.occupations.items()
            if code.startswith("25151")
        ]

        self.assertTrue(nurses)
        self.assertTrue(pharmacists)
        self.assertTrue(all(item.get("assessingAuthority") == "ANMAC" for item in nurses))
        self.assertEqual(self.occupations["411411"].get("assessingAuthority"), "ANMAC")
        self.assertEqual(
            {item["anzsco"]: item.get("assessingAuthority") for item in pharmacists},
            {
                "251511": "APharmC",
                "251512": "VETASSESS",
                "251513": "APharmC",
            },
        )
        for item in pharmacists:
            self.assertEqual(item["lists"], ["CSOL", "STSOL"])
            self.assertNotIn("189", item["visas"])
            self.assertNotIn("485", item["visas"])

    def test_telecommunications_engineering_authorities(self):
        self.assertEqual(
            self.occupations["263311"].get("assessingAuthority"),
            "Engineers Australia",
        )
        self.assertEqual(
            self.occupations["263312"].get("assessingAuthority"),
            "Engineers Australia",
        )


if __name__ == "__main__":
    unittest.main()