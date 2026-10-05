# Copyright 2026 Google LLC
# Seed script for Travel Planner Firestore collection

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-64351d593793"

db = firestore.Client(project=PROJECT_ID)

DESTINATIONS = [
    {
        "id": "tokyo-japan",
        "name": "Tokyo",
        "country": "Japan",
        "category": "Culture & Food",
        "best_time_to_visit": "March to May, September to November",
        "average_daily_budget_usd": 150,
        "highlights": ["Shibuya Crossing", "Senso-ji Temple", "Tsukiji Outer Market", "Akihabara"],
        "description": "A bustling metropolis blending ultra-modern skyscrapers with historic temples and world-class culinary experiences."
    },
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Historic & Nature",
        "best_time_to_visit": "October to November, April",
        "average_daily_budget_usd": 120,
        "highlights": ["Fushimi Inari Shrine", "Arashiyama Bamboo Grove", "Kinkaku-ji (Golden Pavilion)", "Gion District"],
        "description": "Japan's cultural capital, famous for classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses."
    },
    {
        "id": "paris-france",
        "name": "Paris",
        "country": "France",
        "category": "Art & Culinary",
        "best_time_to_visit": "June to August, September to October",
        "average_daily_budget_usd": 180,
        "highlights": ["Eiffel Tower", "Louvre Museum", "Montmartre", "Notre-Dame Cathedral"],
        "description": "The City of Light, global center for art, fashion, gastronomy, and iconic romantic landmarks."
    },
    {
        "id": "rome-italy",
        "name": "Rome",
        "country": "Italy",
        "category": "History & Architecture",
        "best_time_to_visit": "April to May, September to October",
        "average_daily_budget_usd": 140,
        "highlights": ["Colosseum", "Vatican Museums", "Trevi Fountain", "Pantheon"],
        "description": "An open-air museum filled with ancient Roman ruins, Renaissance architecture, and vibrant piazza culture."
    },
    {
        "id": "reykjavik-iceland",
        "name": "Reykjavik",
        "country": "Iceland",
        "category": "Nature & Adventure",
        "best_time_to_visit": "September to March for Northern Lights, June to August for Midnight Sun",
        "average_daily_budget_usd": 200,
        "highlights": ["Blue Lagoon", "Golden Circle", "Hallgrímskirkja", "Northern Lights Tour"],
        "description": "Gateway to Iceland's dramatic volcanic landscapes, geothermal springs, glaciers, and aurora borealis."
    }
]

def seed():
    print(f"Seeding Firestore in project '{PROJECT_ID}'...")
    collection_ref = db.collection("destinations")
    for dest in DESTINATIONS:
        doc_ref = collection_ref.document(dest["id"])
        doc_ref.set(dest)
        print(f"  - Seeded destination: {dest['name']} ({dest['id']})")
    print("Seeding complete!")

if __name__ == "__main__":
    seed()
