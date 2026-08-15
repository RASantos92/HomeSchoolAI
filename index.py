from controller.parent import Parent
from controller.data_manipulation import DataManipulation

dm = DataManipulation()

pc = Parent()
def generateAssessmentTest():
    print("What is your student's name?")
    name = input()

    print("What age is your student?")
    age = input()

    print("What grade level or assumed grade level is your student?")
    grade_level = input()
    pc.assessmentTest(name, age, grade_level)

def generateYearlyPlan():
    print("Whats your students name?")
    name = input()

    print("What is your student's age?")
    age = input()


    print("How many subjects are you trying to create?")
    number_of_subjects = int(input())
    for i in range(number_of_subjects):
        print("Subjects Grade level?")
        grade_level = input()
        print(f"Please input the name of subject {i+1}")
        subject = input()
        pc.createYearlyLessonPlanForSubject(name,age,grade_level,subject)


print('What are you trying to accomplish? \n A) Assessment Test \n B) Generate Year Plan \n C) Generate Weekly Break down. \n D) Create Daily breakdown. \n E) Generate weekly quiz \n F) update weekly plan with new subject \n G) Scan big words')

path = input().upper()

match path:
    case 'A':
        generateAssessmentTest()
    case 'B':
        generateYearlyPlan()
    case 'C':
        print("This requires your students name.")
        name = input()
        print("This also requires the month. \n USE THE NUMBER OF THE MONTH!! \n MM")
        month = input().capitalize()
        print("Last is the week number. \n For example 1,2,3,4. There are only ever 4 weeks of curriculum in each month")
        week_number = input()
        pc.createWeeklyBreakdown(name, month, week_number)
    case 'D':
        print("Whats your students name?")
        name = input()
        print("What is the month? \n USE THE NUMBER OF THE MONTH!! \n MM")
        month = input()
        print("what is the week number? \n This is going to be a number between 1-4 ")
        week = input()
        print("What day? \n Monday - Friday")
        day = input().capitalize()
        pc.createDailyBreakDown(name,month, week, day)
    case 'E':
        print("What is the studnets name?")
        name = input()

        print("what is the month? \n MM!")
        month = input()

        print("what is the week number, example 1-4")
        week = input()

        print("what is the students age?")
        age = input()

        print("what is the students grade?")
        grade = input()

        pc.createWeeklyQuiz(name, month, week, age, grade)
    case "F":
        print("What is your students name?")
        name = input()

        print("What is the new subject?")
        subject_name = input()

        print("What is the student's age?")
        age = input()

        print("What is the student's grade level?")
        grade_level = input()

        pc.updateWeeklylessonPlanWithNewSubject(name, subject_name, age, grade_level)
    case "G":
        lectures = dm.collect_lectures('Hayden')

        for l in lectures:
            big_words = dm.scan_subject_lectures(l.get('lecture'))
            dictionary = dm.build_dictionary(big_words)

        # print(dictionary)





