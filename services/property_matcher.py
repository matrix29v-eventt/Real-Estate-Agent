def match_properties(requirements, properties=None):
    if properties is None:
        from services.database import get_all_properties

        properties = get_all_properties()

    budget_min = requirements.get("budget_min")
    budget_max = requirements.get("budget_max")
    locations = requirements.get("locations", [])
    bhk = requirements.get("bhk")
    min_sqft = requirements.get("min_sqft")
    parking_req = requirements.get("parking")
    furnishing_req = requirements.get("furnishing")
    amenities_req = requirements.get("amenities", [])
    property_type = requirements.get("property_type")

    scored = []
    for prop in properties:
        score = 0
        reasons = []
        total_weight = 0

        location_score_weight = 25
        budget_score_weight = 25
        bhk_score_weight = 15
        sqft_score_weight = 10
        parking_score_weight = 10
        furnishing_score_weight = 5
        amenities_score_weight = 5
        availability_score_weight = 5

        total_weight = (
            location_score_weight
            + budget_score_weight
            + bhk_score_weight
            + sqft_score_weight
            + parking_score_weight
            + furnishing_score_weight
            + amenities_score_weight
            + availability_score_weight
        )

        if locations and prop["location"] in locations:
            score += location_score_weight
            reasons.append(f"Exact location match: {prop['location']}")
        elif locations:
            for loc in locations:
                if loc.lower() in prop["location"].lower():
                    score += int(location_score_weight * 0.5)
                    reasons.append(
                        f"Partial location match: {prop['location']} (similar to {loc})"
                    )
                    break

        if budget_min and budget_max:
            if budget_min <= prop["price"] <= budget_max:
                score += budget_score_weight
                reasons.append(
                    f"Within budget range ({budget_min / 100000:.1f}-{budget_max / 100000:.1f}L)"
                )
            elif prop["price"] < budget_min:
                score += int(budget_score_weight * 0.8)
                reasons.append(
                    f"Below budget ({prop['price'] / 100000:.1f}L < {budget_min / 100000:.1f}L)"
                )
            else:
                score += int(budget_score_weight * 0.2)
                reasons.append(
                    f"Above budget ({prop['price'] / 100000:.1f}L > {budget_max / 100000:.1f}L)"
                )
        elif budget_min and prop["price"] >= budget_min:
            score += int(budget_score_weight * 0.7)
            reasons.append(f"At or above minimum budget")
        elif budget_max and prop["price"] <= budget_max:
            score += int(budget_score_weight * 0.7)
            reasons.append(f"Within maximum budget")

        if bhk and prop["bhk"] >= bhk:
            score += bhk_score_weight
            reasons.append(f"{prop['bhk']}BHK meets {bhk}BHK requirement")
        elif bhk and prop["bhk"] < bhk:
            reasons.append(f"Only {prop['bhk']}BHK, less than {bhk}BHK required")

        if min_sqft and prop["sqft"] >= min_sqft:
            score += sqft_score_weight
            reasons.append(f"Square footage sufficient ({prop['sqft']} sqft)")
        elif min_sqft:
            reasons.append(
                f"Square footage below requirement ({prop['sqft']} < {min_sqft})"
            )

        if parking_req and prop["parking"] >= parking_req:
            score += parking_score_weight
            reasons.append(f"Parking available ({prop['parking']} slots)")
        elif parking_req:
            reasons.append(
                f"Insufficient parking ({prop['parking']} < {parking_req} required)"
            )
        elif parking_req is None:
            score += int(parking_score_weight * 0.5)

        if furnishing_req and prop["furnishing"].lower() == furnishing_req.lower():
            score += furnishing_score_weight
            reasons.append(f"Furnishing matches: {prop['furnishing']}")
        elif furnishing_req is None:
            score += int(furnishing_score_weight * 0.5)

        if amenities_req:
            prop_amenities = [a.strip().lower() for a in prop["amenities"].split(",")]
            matched_amenities = 0
            for amenity in amenities_req:
                for pa in prop_amenities:
                    if amenity.lower() in pa.lower():
                        matched_amenities += 1
                        break
            if matched_amenities > 0:
                score += int(
                    amenities_score_weight * (matched_amenities / len(amenities_req))
                )
                reasons.append(
                    f"Matched {matched_amenities}/{len(amenities_req)} amenities"
                )
            else:
                reasons.append("No matching amenities")

        if prop["availability"] == "Ready to Move":
            score += availability_score_weight
            reasons.append("Ready to move")
        elif prop["availability"] == "Under Construction":
            reasons.append("Under construction")

        final_score = int((score / total_weight) * 100) if total_weight > 0 else 0
        if final_score >= 50:
            scored.append(
                {"property": prop, "match_score": final_score, "reasons": reasons}
            )

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:5]
