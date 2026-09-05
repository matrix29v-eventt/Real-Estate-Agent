"""Synthetic property inventory for the Thiruvananthapuram (Trivandrum) market.

The dataset is deliberately *uneven*: premium areas have no affordable stock,
some records are sold out or on hold, several projects are still under
construction, and 4BHK inventory only exists above Rs 1.4 Cr. That unevenness is
what lets the agent demonstrate real reasoning instead of always finding a match.

Prices are whole rupees. Areas and price-per-sqft bands are modelled on the
Trivandrum market; project names and builders are fictional.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

# (id, name, location, type, bhk, price, sqft, parking, furnishing,
#  amenities, availability, builder, possession_status, possession_date, tags)
_ROWS = [
    # ---------------- Kazhakkoottam (IT corridor) ----------------
    ("P001", "Confident Aquila", "Kazhakkoottam", "Apartment", 3, 7_200_000, 1420, 1, "Semi-Furnished",
     "Gated Community,Gym,Power Backup,Security,Lift,Children Play Area", "AVAILABLE", "Confident Group",
     "Ready to Move", None, "technopark-nearby,family,ready-to-move,gated-community,high-demand"),
    ("P002", "Asset Silver Sands", "Kazhakkoottam", "Apartment", 2, 5_400_000, 1050, 1, "Unfurnished",
     "Lift,Security,Power Backup,Rain Water Harvesting", "AVAILABLE", "Asset Homes",
     "Ready to Move", None, "technopark-nearby,budget,ready-to-move"),
    ("P003", "Skyline Ivy League", "Kazhakkoottam", "Apartment", 3, 7_800_000, 1560, 1, "Semi-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,CCTV", "AVAILABLE", "Skyline Builders",
     "Ready to Move", None, "technopark-nearby,premium,gated-community,ready-to-move"),
    ("P004", "Heera Waterfront", "Kazhakkoottam", "Apartment", 2, 4_850_000, 980, 1, "Unfurnished",
     "Lift,Security,Power Backup", "AVAILABLE", "Heera Homes",
     "Under Construction", "2026-12-31", "technopark-nearby,budget,investment"),
    ("P005", "SFS Green Valley", "Kazhakkoottam", "Apartment", 3, 6_900_000, 1380, 1, "Semi-Furnished",
     "Gated Community,Gym,Children Play Area,Power Backup,Security,Lift,Jogging Track", "AVAILABLE", "SFS Homes",
     "Ready to Move", None, "technopark-nearby,family,ready-to-move,gated-community"),
    ("P006", "Artech Aster Villas", "Kazhakkoottam", "Villa", 4, 18_500_000, 2600, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Clubhouse,Landscaped Garden,Security,Solar Water Heating", "AVAILABLE",
     "Artech Realtors", "Ready to Move", None, "premium,family,gated-community,technopark-nearby"),
    ("P007", "Kazhakkoottam Residential Plot", "Kazhakkoottam", "Plot", None, 6_200_000, 2400, 0, "Unfurnished",
     "Gated Community,Security", "SOLD_OUT", "Trivandrum Builders",
     "Ready to Move", None, "investment,technopark-nearby"),

    # ---------------- Technopark vicinity ----------------
    ("P008", "Technopark Heights", "Technopark", "Apartment", 3, 7_450_000, 1450, 1, "Semi-Furnished",
     "Gated Community,Gym,Power Backup,Security,Lift,Intercom,CCTV", "AVAILABLE", "Confident Group",
     "Ready to Move", None, "technopark-nearby,family,ready-to-move,gated-community,high-demand"),
    ("P009", "Nikunjam Emerald", "Technopark", "Apartment", 2, 5_800_000, 1120, 1, "Unfurnished",
     "Lift,Security,Power Backup,Children Play Area", "AVAILABLE", "Nikunjam Constructions",
     "Ready to Move", None, "technopark-nearby,ready-to-move,high-demand"),
    ("P010", "Trivandrum Tech Residency", "Technopark", "Apartment", 1, 3_200_000, 620, 1, "Fully-Furnished",
     "Lift,Security,Power Backup", "AVAILABLE", "Trivandrum Builders",
     "Ready to Move", None, "budget,investment,technopark-nearby,ready-to-move"),
    ("P011", "PVS Techno Enclave", "Technopark", "Apartment", 3, 8_800_000, 1620, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,Indoor Games", "AVAILABLE", "PVS Builders",
     "Ready to Move", None, "premium,technopark-nearby,gated-community,ready-to-move"),
    ("P012", "Sreedhanya Tech Court", "Technopark", "Apartment", 3, 6_650_000, 1340, 1, "Semi-Furnished",
     "Gated Community,Gym,Power Backup,Security,Lift", "AVAILABLE", "Sreedhanya Homes",
     "Under Construction", "2027-02-28", "technopark-nearby,family,gated-community"),

    # ---------------- Sreekaryam ----------------
    ("P013", "Jain Sreekaryam Meadows", "Sreekaryam", "Apartment", 2, 5_100_000, 1010, 1, "Unfurnished",
     "Lift,Security,Power Backup,Rain Water Harvesting", "AVAILABLE", "Jain Housing",
     "Ready to Move", None, "budget,family,ready-to-move"),
    ("P014", "Asset Aura", "Sreekaryam", "Apartment", 3, 6_400_000, 1300, 1, "Semi-Furnished",
     "Gated Community,Gym,Children Play Area,Security,Lift", "AVAILABLE", "Asset Homes",
     "Ready to Move", None, "family,ready-to-move,gated-community,technopark-nearby"),
    ("P015", "Malabar Orchid", "Sreekaryam", "Apartment", 3, 7_100_000, 1480, 1, "Semi-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security", "AVAILABLE", "Malabar Developers",
     "Under Construction", "2027-03-31", "family,gated-community,investment"),
    ("P016", "Sreekaryam Residential Plot", "Sreekaryam", "Plot", None, 4_700_000, 2178, 0, "Unfurnished",
     "Security", "AVAILABLE", "Trivandrum Builders",
     "Ready to Move", None, "investment,budget"),
    ("P017", "Heera Sreekaryam Court", "Sreekaryam", "Apartment", 2, 4_450_000, 940, 0, "Unfurnished",
     "Lift,Security", "ON_HOLD", "Heera Homes",
     "Ready to Move", None, "budget"),

    # ---------------- Akkulam ----------------
    ("P018", "Confident Lake View", "Akkulam", "Apartment", 3, 8_200_000, 1520, 1, "Semi-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,Landscaped Garden", "AVAILABLE", "Confident Group",
     "Ready to Move", None, "premium,technopark-nearby,gated-community,ready-to-move,high-demand"),
    ("P019", "Akkulam Bay Residency", "Akkulam", "Apartment", 2, 5_700_000, 1080, 1, "Unfurnished",
     "Lift,Security,Power Backup,CCTV", "AVAILABLE", "Nikunjam Constructions",
     "Ready to Move", None, "technopark-nearby,ready-to-move"),
    ("P020", "Skyline Lakeshore Villa", "Akkulam", "Villa", 4, 21_000_000, 2800, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Clubhouse,Landscaped Garden,Security,Solar Water Heating", "AVAILABLE",
     "Skyline Builders", "Ready to Move", None, "premium,family,gated-community"),
    ("P021", "Asset Akkulam Blue", "Akkulam", "Apartment", 3, 7_400_000, 1390, 1, "Semi-Furnished",
     "Gated Community,Gym,Security,Lift,Children Play Area", "AVAILABLE", "Asset Homes",
     "Under Construction", "2026-09-30", "technopark-nearby,family,gated-community"),

    # ---------------- Ulloor ----------------
    ("P022", "Artech Ulloor Grand", "Ulloor", "Apartment", 3, 7_000_000, 1420, 1, "Semi-Furnished",
     "Gated Community,Gym,Security,Lift,Power Backup", "AVAILABLE", "Artech Realtors",
     "Ready to Move", None, "family,ready-to-move,gated-community"),
    ("P023", "Ulloor Garden Homes", "Ulloor", "Apartment", 2, 4_900_000, 990, 1, "Unfurnished",
     "Lift,Security,Landscaped Garden", "AVAILABLE", "Trivandrum Builders",
     "Ready to Move", None, "budget,family,ready-to-move"),
    ("P024", "SFS Ulloor Crest", "Ulloor", "Apartment", 3, 8_500_000, 1610, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,Indoor Games", "AVAILABLE", "SFS Homes",
     "Ready to Move", None, "premium,gated-community,ready-to-move"),
    ("P025", "Ulloor Builder Floor Residency", "Ulloor", "Builder Floor", 2, 5_500_000, 1150, 1, "Semi-Furnished",
     "Security,Power Backup", "AVAILABLE", "Jain Housing",
     "Ready to Move", None, "family,ready-to-move"),

    # ---------------- Pattom ----------------
    ("P026", "Nikunjam Pattom Royale", "Pattom", "Apartment", 3, 9_600_000, 1550, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,CCTV", "AVAILABLE", "Nikunjam Constructions",
     "Ready to Move", None, "premium,gated-community,ready-to-move,high-demand"),
    ("P027", "Pattom Central Apartments", "Pattom", "Apartment", 2, 6_200_000, 1020, 1, "Semi-Furnished",
     "Lift,Security,Power Backup", "AVAILABLE", "Trivandrum Builders",
     "Ready to Move", None, "ready-to-move,investment"),
    ("P028", "Heera Pattom Signature", "Pattom", "Apartment", 3, 11_200_000, 1720, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,Jogging Track", "AVAILABLE", "Heera Homes",
     "Ready to Move", None, "premium,gated-community,ready-to-move"),
    ("P029", "Pattom Corner Plot", "Pattom", "Plot", None, 7_800_000, 1742, 0, "Unfurnished",
     "Security", "AVAILABLE", "Malabar Developers",
     "Ready to Move", None, "investment,premium"),

    # ---------------- Kowdiar (premium only) ----------------
    ("P030", "Kowdiar Palace View", "Kowdiar", "Apartment", 3, 16_500_000, 1850, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,Landscaped Garden,Intercom", "AVAILABLE",
     "Skyline Builders", "Ready to Move", None, "premium,gated-community,ready-to-move,high-demand"),
    ("P031", "Confident Kowdiar Elite", "Kowdiar", "Apartment", 4, 24_500_000, 2450, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Gym,Clubhouse,Security,Lift,Indoor Games,CCTV", "AVAILABLE", "Confident Group",
     "Ready to Move", None, "premium,family,gated-community,ready-to-move"),
    ("P032", "Kowdiar Signature Villa", "Kowdiar", "Villa", 4, 32_000_000, 3200, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Clubhouse,Landscaped Garden,Security,Solar Water Heating", "AVAILABLE",
     "Artech Realtors", "Ready to Move", None, "premium,family,gated-community"),
    ("P033", "Skyline Kowdiar Court", "Kowdiar", "Apartment", 3, 14_800_000, 1700, 1, "Semi-Furnished",
     "Gated Community,Gym,Clubhouse,Security,Lift", "AVAILABLE", "Skyline Builders",
     "Under Construction", "2026-10-31", "premium,gated-community"),
    ("P034", "Kowdiar Residency", "Kowdiar", "Apartment", 2, 9_500_000, 1250, 1, "Semi-Furnished",
     "Lift,Security,Power Backup,CCTV", "AVAILABLE", "Jain Housing",
     "Ready to Move", None, "premium,ready-to-move"),

    # ---------------- Vazhuthacaud ----------------
    ("P035", "Vazhuthacaud Heritage", "Vazhuthacaud", "Apartment", 3, 12_500_000, 1600, 1, "Fully-Furnished",
     "Gated Community,Gym,Clubhouse,Security,Lift,Intercom", "AVAILABLE", "Heera Homes",
     "Ready to Move", None, "premium,gated-community,ready-to-move"),
    ("P036", "Artech Vazhuthacaud Pearl", "Vazhuthacaud", "Apartment", 2, 8_200_000, 1150, 1, "Semi-Furnished",
     "Lift,Security,Power Backup,CCTV", "AVAILABLE", "Artech Realtors",
     "Ready to Move", None, "premium,ready-to-move,investment"),
    ("P037", "Jain Vazhuthacaud Towers", "Vazhuthacaud", "Apartment", 3, 10_800_000, 1480, 1, "Semi-Furnished",
     "Gated Community,Gym,Security,Lift,Power Backup", "AVAILABLE", "Jain Housing",
     "Ready to Move", None, "premium,family,gated-community"),
    ("P038", "Vazhuthacaud Builder Floor", "Vazhuthacaud", "Builder Floor", 4, 15_500_000, 2100, 1, "Unfurnished",
     "Security,Power Backup", "SOLD_OUT", "Trivandrum Builders",
     "Ready to Move", None, "premium,family"),

    # ---------------- Peroorkada ----------------
    ("P039", "Peroorkada Green Nest", "Peroorkada", "Apartment", 2, 4_300_000, 960, 1, "Unfurnished",
     "Lift,Security", "AVAILABLE", "Trivandrum Builders",
     "Ready to Move", None, "budget,family,ready-to-move"),
    ("P040", "Asset Peroorkada Woods", "Peroorkada", "Apartment", 3, 6_100_000, 1320, 1, "Semi-Furnished",
     "Gated Community,Children Play Area,Security,Lift,Landscaped Garden", "AVAILABLE", "Asset Homes",
     "Ready to Move", None, "family,ready-to-move,gated-community"),
    ("P041", "Peroorkada Villa Grove", "Peroorkada", "Villa", 3, 10_500_000, 1900, 1, "Semi-Furnished",
     "Gated Community,Landscaped Garden,Security,Solar Water Heating", "AVAILABLE", "Malabar Developers",
     "Ready to Move", None, "family,gated-community,ready-to-move"),
    ("P042", "Peroorkada Residential Plot", "Peroorkada", "Plot", None, 5_100_000, 2613, 0, "Unfurnished",
     "Security", "AVAILABLE", "Sreedhanya Homes",
     "Ready to Move", None, "investment,budget"),

    # ---------------- Kesavadasapuram ----------------
    ("P043", "Kesavadasapuram Skyline", "Kesavadasapuram", "Apartment", 2, 5_200_000, 1000, 1, "Unfurnished",
     "Lift,Security,Power Backup", "AVAILABLE", "Skyline Builders",
     "Ready to Move", None, "budget,ready-to-move,family"),
    ("P044", "SFS Kesava Heights", "Kesavadasapuram", "Apartment", 3, 6_700_000, 1360, 1, "Semi-Furnished",
     "Gated Community,Gym,Security,Lift,Children Play Area", "AVAILABLE", "SFS Homes",
     "Ready to Move", None, "family,ready-to-move,gated-community"),
    ("P045", "Kesavadasapuram Compact Homes", "Kesavadasapuram", "Apartment", 1, 2_900_000, 580, 0, "Semi-Furnished",
     "Lift,Security", "AVAILABLE", "Heera Homes",
     "Ready to Move", None, "budget,investment,ready-to-move"),
    ("P046", "Heera Kesava Court", "Kesavadasapuram", "Apartment", 3, 7_300_000, 1450, 1, "Semi-Furnished",
     "Gated Community,Gym,Clubhouse,Security,Lift", "AVAILABLE", "Heera Homes",
     "Under Construction", "2026-11-30", "family,gated-community"),

    # ---------------- Thampanoor ----------------
    ("P047", "Thampanoor City Square", "Thampanoor", "Apartment", 2, 4_100_000, 900, 0, "Unfurnished",
     "Lift,Security", "AVAILABLE", "Trivandrum Builders",
     "Ready to Move", None, "budget,investment,ready-to-move"),
    ("P048", "Thampanoor Metro Residency", "Thampanoor", "Apartment", 1, 2_750_000, 560, 0, "Semi-Furnished",
     "Lift,Security,CCTV", "AVAILABLE", "Nikunjam Constructions",
     "Ready to Move", None, "budget,investment,ready-to-move"),
    ("P049", "Thampanoor Junction Residency", "Thampanoor", "Apartment", 3, 5_800_000, 1300, 1, "Unfurnished",
     "Lift,Security,Power Backup", "AVAILABLE", "Jain Housing",
     "Ready to Move", None, "budget,investment,ready-to-move"),

    # ---------------- Poojappura ----------------
    ("P050", "Poojappura Serene Homes", "Poojappura", "Apartment", 2, 4_750_000, 1030, 1, "Unfurnished",
     "Lift,Security,Children Play Area", "AVAILABLE", "Sreedhanya Homes",
     "Ready to Move", None, "budget,family,ready-to-move"),
    ("P051", "Asset Poojappura Vista", "Poojappura", "Apartment", 3, 6_600_000, 1400, 1, "Semi-Furnished",
     "Gated Community,Gym,Security,Lift,Jogging Track", "AVAILABLE", "Asset Homes",
     "Ready to Move", None, "family,ready-to-move,gated-community"),
    ("P052", "Poojappura Grand Villa", "Poojappura", "Villa", 4, 14_200_000, 2400, 1, "Fully-Furnished",
     "Gated Community,Swimming Pool,Landscaped Garden,Security,Solar Water Heating", "AVAILABLE",
     "Malabar Developers", "Ready to Move", None, "premium,family,gated-community,ready-to-move"),
    ("P053", "Poojappura Residential Plot", "Poojappura", "Plot", None, 3_800_000, 2178, 0, "Unfurnished",
     "Security", "SOLD_OUT", "Trivandrum Builders",
     "Ready to Move", None, "investment,budget"),
]

_FIELDS = (
    "property_id", "name", "location", "property_type", "bhk", "price", "sqft",
    "parking", "furnishing", "amenities", "availability", "builder",
    "possession_status", "possession_date", "tags",
)

_LISTING_EPOCH = date(2025, 10, 1)


def property_rows() -> List[Dict[str, Any]]:
    """Return the seed inventory as dicts ready for SQLite insertion."""
    rows: List[Dict[str, Any]] = []
    for offset, values in enumerate(_ROWS):
        row = dict(zip(_FIELDS, values))
        # Stagger listing dates so the dashboard looks like a real pipeline.
        row["created_at"] = (_LISTING_EPOCH + timedelta(days=offset * 3)).isoformat()
        rows.append(row)
    return rows


if __name__ == "__main__":  # pragma: no cover - quick sanity check
    rows = property_rows()
    print(f"{len(rows)} properties")
    ids = [r["property_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate property_id"
