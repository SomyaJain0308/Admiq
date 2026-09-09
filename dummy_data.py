import random
import time
import requests

BASE_URL = "https://admiq-0693.onrender.com"
ENDPOINT = f"{BASE_URL}/router/test/chat"
COLLEGE_ID = 2
DELAY_SECONDS = 1.5  # be polite to a free-tier Render instance

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
    "Ishaan", "Rohan", "Ananya", "Diya", "Saanvi", "Aadhya", "Kiara", "Myra",
    "Priya", "Neha", "Riya", "Isha", "Kabir", "Aryan", "Dev", "Rahul", "Sneha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Reddy", "Patel", "Singh",
    "Mehta", "Chopra", "Bansal", "Kapoor", "Joshi", "Malhotra", "Rao",
]

def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def random_phone():
    # Indian-style 10-digit mobile number, starting 6-9, avoiding real-looking clashes
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))

# Each conversation is a list of student messages, in order.
# Pick topics/wording that read like genuine prospective-student enquiries.
CONVERSATION_TEMPLATES = [
    [
        "Hi, does JIIT offer B.Tech in AI and Data Science?",
        "What's the total fee for that program?",
        "Is there any entrance exam or is it based on JEE Mains score?",
        "What's the last date to apply for this year?",
    ],
    [
        "Hello, I wanted to know about hostel facilities for girls",
        "Is it compulsory to stay in hostel for 1st year students?",
        "What's the hostel fee per year, and is food included?",
        "Ok thank you, one more thing - is wifi available in hostel rooms?",
    ],
    [
        "Hi, what branches are available under B.Tech CSE?",
        "Which one has better placements - core CSE or AI/ML specialization?",
        "Can you tell me the average package and top recruiters?",
        "That's helpful. What's the fee structure for CSE?",
        "Is there any scholarship for students with 90%+ in 12th?",
    ],
    [
        "hlo, i want info about mechanical engineering course",
        "what is the eligibility criteria for mechanical branch?",
        "do you have lateral entry for diploma students?",
        "what's the fee for lateral entry students",
    ],
    [
        "Hi I'm an NRI student, what's the fee difference for NRI category?",
        "Is the admission process different for NRI students?",
        "Do NRI students need any additional documents?",
        "Is there any quota reserved for NRI seats or is it open category?",
    ],
    [
        "Hey, does the college have an MBA program?",
        "What's the eligibility - do I need CAT/MAT score?",
        "What's the fee for MBA and is it 1 year or 2 years?",
        "Are there any placement stats for the MBA batch?",
    ],
    [
        "Hi, I belong to SC category, are there any fee concessions?",
        "What documents do I need to submit for the category certificate?",
        "Is the fee waiver applicable every year or only first year?",
        "Thank you, this is really helpful",
    ],
    [
        "Hello, what's the difference between BTech IT and BTech CSE here?",
        "Which one is easier to get into based on cutoff?",
        "Is there any bridge course before semester starts for weak students?",
        "Okay, and what's the refund policy if I want to withdraw admission?",
    ],
]

def send_message(student_phone: str, student_name: str, message: str):
    payload = {
        "college_id": COLLEGE_ID,
        "student_phone": student_phone,
        "message": message,
        "student_name": student_name,
    }
    resp = requests.post(ENDPOINT, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()

def run():
    random.shuffle(CONVERSATION_TEMPLATES)
    for convo in CONVERSATION_TEMPLATES:
        name = random_name()
        phone = random_phone()
        print(f"\n=== Starting conversation for {name} ({phone}) ===")
        for i, msg in enumerate(convo, start=1):
            try:
                data = send_message(phone, name, msg)
            except requests.RequestException as e:
                print(f"  [{i}] FAILED to send '{msg}': {e}")
                continue
            print(f"  [{i}] Student: {msg}")
            print(f"      Assistant: {data.get('response')}")
            time.sleep(DELAY_SECONDS)

if __name__ == "__main__":
    run()