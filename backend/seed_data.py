import os
import django
import random

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from exams.models import PracticeTest, Module, Question;

def create_math_questions(module, count, target_sum):
    print(f"Creating {count} math questions for module {module.id} (target: {target_sum})...")
    scores = [10, 20, 40]
    current_sum = 0
    
    for i in range(count):
        remaining_count = count - i - 1
        # Pick a score that keeps us on track to reach target_sum
        if remaining_count > 0:
            # Try to pick a score that leaves at least 10 points for each remaining question
            # and doesn't exceed target - (10 * remaining_count)
            max_possible = target_sum - current_sum - (10 * remaining_count)
            available_scores = [s for s in scores if s <= max_possible]
            if not available_scores: available_scores = [10]
            score = random.choice(available_scores)
        else:
            # Last question gets the remainder
            score = target_sum - current_sum
        
        current_sum += score
        is_spr = (i >= count - 5) # Last 5 are SPR
        
        Question.objects.create(
            module=module,
            question_type="MATH",
            question_text=f"Sample Math Question {i+1}: What is the value of {random.randint(2,20)}x + {random.randint(1,10)} if x = {random.randint(1,5)}?",
            is_math_input=is_spr,
            correct_answers=str(random.randint(1,100)) if not is_spr else f"{random.randint(1,100)}",
            option_a="10", option_b="20", option_c="30", option_d="40", # Placeholders for MCQ
            score=score
        )
    print(f"Module {module.id} created with total score: {current_sum}")

def create_english_questions(module, count, target_sum):
    print(f"Creating {count} english questions for module {module.id} (target: {target_sum})...")
    scores = [10, 20, 40]
    current_sum = 0
    
    for i in range(count):
        remaining_count = count - i - 1
        if remaining_count > 0:
            max_possible = target_sum - current_sum - (10 * remaining_count)
            available_scores = [s for s in scores if s <= max_possible]
            if not available_scores: available_scores = [10]
            score = random.choice(available_scores)
        else:
            score = target_sum - current_sum
            
        current_sum += score
        q_type = random.choice(["READING", "WRITING"])
        
        Question.objects.create(
            module=module,
            question_type=q_type,
            question_text=f"Sample {q_type} Text {i+1}: The researchers found that the data was consistent with their hypothesis about {random.choice(['climate', 'history', 'biology', 'art'])}.",
            question_prompt=f"Which choice most logically completes the text?",
            option_a="Option A text", option_b="Option B text", option_c="Option C text", option_d="Option D text",
            correct_answers=random.choice(["A", "B", "C", "D"]),
            score=score
        )
    print(f"Module {module.id} created with total score: {current_sum}")

def seed_full_test():
    # 1. English
    eng_test = PracticeTest.objects.create(title="Full SAT English Example", subject="READING_WRITING")
    m1_eng = Module.objects.create(practice_test=eng_test, module_order=1, time_limit_minutes=32)
    create_english_questions(m1_eng, 27, 330) # 530 - 200 = 330
    m2_eng = Module.objects.create(practice_test=eng_test, module_order=2, time_limit_minutes=32)
    create_english_questions(m2_eng, 27, 270) # 270 - 0 = 270

    # 2. Math
    math_test = PracticeTest.objects.create(title="Full SAT Math Example", subject="MATH")
    m1_math = Module.objects.create(practice_test=math_test, module_order=1, time_limit_minutes=35)
    create_math_questions(m1_math, 22, 380) # 580 - 200 = 380
    m2_math = Module.objects.create(practice_test=math_test, module_order=2, time_limit_minutes=35)
    create_math_questions(m2_math, 22, 220) # 220 - 0 = 220

    print("Successfully seeded full SAT data with correct question counts and scores.")

if __name__ == "__main__":
    PracticeTest.objects.filter(title__icontains="Full SAT").delete()
    seed_full_test()
