"""Seed demo inventory for Premier Auto Group so the AI has vehicles to discuss."""
from app.db import init_db, get_session_factory
from app.models import Dealer, Vehicle

init_db()
sf = get_session_factory()
s = sf()

dealer = s.query(Dealer).filter(Dealer.slug == "premier-auto").first()
if not dealer:
    print("No premier-auto dealer found!")
    exit(1)

# Check if inventory already exists
existing = s.query(Vehicle).filter(Vehicle.dealer_id == dealer.id).count()
if existing > 0:
    print(f"Already have {existing} vehicles — skipping seed.")
    exit(0)

vehicles = [
    {
        "stock_no": "PA-1001", "vin": "1HGBH41JXMN109186", "year": 2023,
        "make": "Honda", "model": "Civic", "trim": "Sport",
        "body": "Sedan", "mileage": 18200, "price": 28900, "status": "available",
        "raw": {
            "engine": "2.0L 4-cyl", "transmission": "CVT", "drivetrain": "FWD",
            "horsepower": "158 hp", "fuel_economy": "7.1 L/100km combined",
            "exterior_color": "Crystal Black Pearl", "interior": "Black Cloth",
            "features": ["Apple CarPlay", "Android Auto", "Honda Sensing Suite", "Sunroof", "LED Headlights"]
        }
    },
    {
        "stock_no": "PA-1002", "vin": "3MYDLBHV5PY123456", "year": 2023,
        "make": "Mazda", "model": "CX-5", "trim": "GX",
        "body": "SUV", "mileage": 14500, "price": 31200, "status": "available",
        "raw": {
            "engine": "2.5L 4-cyl", "transmission": "6-speed automatic", "drivetrain": "AWD",
            "horsepower": "187 hp", "fuel_economy": "8.1 L/100km combined",
            "exterior_color": "Soul Red Crystal", "interior": "Black Leatherette",
            "features": ["i-Activ AWD", "Mazda Connect", "Bose Audio", "Heated Seats", "Blind Spot Monitoring"]
        }
    },
    {
        "stock_no": "PA-1003", "vin": "5YFBURHE5NP012345", "year": 2024,
        "make": "Toyota", "model": "RAV4", "trim": "LE",
        "body": "SUV", "mileage": 5200, "price": 35800, "status": "available",
        "raw": {
            "engine": "2.5L 4-cyl", "transmission": "8-speed automatic", "drivetrain": "AWD",
            "horsepower": "203 hp", "fuel_economy": "7.8 L/100km combined",
            "exterior_color": "Magnetic Grey Metallic", "interior": "Black Fabric",
            "features": ["Toyota Safety Sense 2.5", "Android Auto", "Apple CarPlay", "AWD", "Roof Rails"]
        }
    },
    {
        "stock_no": "PA-1004", "vin": "2T3BFREV5NW123456", "year": 2022,
        "make": "Hyundai", "model": "Tucson", "trim": "Preferred",
        "body": "SUV", "mileage": 22000, "price": 29900, "status": "available",
        "raw": {
            "engine": "2.5L 4-cyl", "transmission": "8-speed automatic", "drivetrain": "AWD",
            "horsepower": "187 hp", "fuel_economy": "8.4 L/100km combined",
            "exterior_color": "Shimmering Silver", "interior": "Grey Leather",
            "features": ["SmartSense Safety", "10.25\" Touchscreen", "Wireless Charging", "Panoramic Sunroof", "Heated Steering Wheel"]
        }
    },
    {
        "stock_no": "PA-1005", "vin": "WBA5R1C50LA123456", "year": 2023,
        "make": "BMW", "model": "X3", "trim": "xDrive30i",
        "body": "SUV", "mileage": 16800, "price": 48500, "status": "available",
        "raw": {
            "engine": "2.0L Turbo 4-cyl", "transmission": "8-speed automatic", "drivetrain": "AWD",
            "horsepower": "248 hp", "fuel_economy": "8.7 L/100km combined",
            "exterior_color": "Alpine White", "interior": "Black Vernasca Leather",
            "features": ["BMW Live Cockpit", "Harman Kardon", "Panoramic Roof", "Driving Assistant", "Sport Seats"]
        }
    },
    {
        "stock_no": "PA-1006", "vin": "1N4BL4CV5PN123456", "year": 2023,
        "make": "Nissan", "model": "Altima", "trim": "SV",
        "body": "Sedan", "mileage": 21000, "price": 26500, "status": "available",
        "raw": {
            "engine": "2.5L 4-cyl", "transmission": "CVT", "drivetrain": "FWD",
            "horsepower": "188 hp", "fuel_economy": "7.6 L/100km combined",
            "exterior_color": "Brilliant Silver", "interior": "Charcoal Cloth",
            "features": ["Nissan Safety Shield 360", "ProPILOT Assist", "8\" Touchscreen", "Remote Start", "LED Headlights"]
        }
    },
    {
        "stock_no": "PA-1007", "vin": "1C4RJFAG5NC123456", "year": 2024,
        "make": "Jeep", "model": "Wrangler", "trim": "Sport S",
        "body": "SUV", "mileage": 3400, "price": 42000, "status": "available",
        "raw": {
            "engine": "3.6L V6", "transmission": "8-speed automatic", "drivetrain": "4WD",
            "horsepower": "285 hp", "fuel_economy": "11.2 L/100km combined",
            "exterior_color": "Sarge Green", "interior": "Black Cloth",
            "features": ["Uconnect 5", "Removable Top", "Skid Plates", "Tow Hooks", "LED Lighting Group"]
        }
    },
    {
        "stock_no": "PA-1008", "vin": "5XYZU3LB5PG123456", "year": 2023,
        "make": "Kia", "model": "Sportage", "trim": "EX",
        "body": "SUV", "mileage": 19500, "price": 33400, "status": "available",
        "raw": {
            "engine": "2.5L 4-cyl", "transmission": "8-speed automatic", "drivetrain": "AWD",
            "horsepower": "187 hp", "fuel_economy": "8.3 L/100km combined",
            "exterior_color": "Gravity Grey", "interior": "Black SynTex Leather",
            "features": ["Dual Panoramic Display", "Harman Kardon", "Blind-Spot View Monitor", "Heated/Ventilated Seats", "Smart Power Liftgate"]
        }
    },
    {
        "stock_no": "PA-1009", "vin": "2T1BURHE0NC123456", "year": 2022,
        "make": "Toyota", "model": "Corolla", "trim": "SE",
        "body": "Sedan", "mileage": 28000, "price": 23900, "status": "available",
        "raw": {
            "engine": "2.0L 4-cyl", "transmission": "CVT", "drivetrain": "FWD",
            "horsepower": "169 hp", "fuel_economy": "6.9 L/100km combined",
            "exterior_color": "Blue Crush Metallic", "interior": "Black Fabric Sport",
            "features": ["Toyota Safety Sense 2.0", "8\" Touchscreen", "Apple CarPlay", "Android Auto", "Sport-Tuned Suspension"]
        }
    },
    {
        "stock_no": "PA-1010", "vin": "1FTFW1E8XNF123456", "year": 2023,
        "make": "Ford", "model": "F-150", "trim": "XLT",
        "body": "Truck", "mileage": 12800, "price": 52000, "status": "available",
        "raw": {
            "engine": "2.7L EcoBoost V6", "transmission": "10-speed automatic", "drivetrain": "4WD",
            "horsepower": "325 hp", "fuel_economy": "11.0 L/100km combined",
            "exterior_color": "Iconic Silver", "interior": "Medium Dark Slate Cloth",
            "features": ["SYNC 4", "12\" Touchscreen", "Pro Power Onboard", "360-Degree Camera", "Tailgate Step"]
        }
    },
]

for v in vehicles:
    veh = Vehicle(dealer_id=dealer.id, **v)
    s.add(veh)

s.commit()
print(f"Seeded {len(vehicles)} vehicles for {dealer.slug}")
s.close()
