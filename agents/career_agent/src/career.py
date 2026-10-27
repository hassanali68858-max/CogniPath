
import json
from pathlib import Path
from rdflib import Graph


# Load Career Ontology
graph = Graph()
ontology_path = Path(__file__).resolve().parent.parent / "ontology" / "career.owl"
graph.parse(str(ontology_path), format="xml")

print("Career Ontology loaded successfully!")
print("Total RDF triples:", len(graph))

# 1. Student Skills
skill_query = """
PREFIX career: <https://example.org/cognipath/career#>

SELECT ?skill
WHERE {
    career:ElhamPournouri career:hasSkill ?skill .
}
"""

print("\nStudent Skills:")
for row in graph.query(skill_query):
    print(row.skill.split("#")[-1])

# 2. Skill Gap Analysis
gap_query = """
PREFIX career: <https://example.org/cognipath/career#>

SELECT ?opportunity ?missingSkill
WHERE {
    ?opportunity career:requiresSkill ?missingSkill .

    FILTER NOT EXISTS {
        career:ElhamPournouri career:hasSkill ?missingSkill .
    }
}
"""

print("\nSkill Gap Analysis:")
for row in graph.query(gap_query):
    opportunity = row.opportunity.split("#")[-1]
    skill = row.missingSkill.split("#")[-1]

    print("Opportunity:", opportunity)
    print("Missing Skill:", skill)

# 3. Learning Recommendation
recommendation_query = """
PREFIX career: <https://example.org/cognipath/career#>

SELECT ?missingSkill ?resource ?url
WHERE {
    ?opportunity career:requiresSkill ?missingSkill .

    FILTER NOT EXISTS {
        career:ElhamPournouri career:hasSkill ?missingSkill .
    }

    ?resource career:helpsLearnSkill ?missingSkill .
    ?resource career:resourceURL ?url .
}
"""

print("\nLearning Recommendations:")

for row in graph.query(recommendation_query):
    skill = row.missingSkill.split("#")[-1]
    resource = row.resource.split("#")[-1]
    url = str(row.url)

    print("Missing Skill:", skill)
    print("Recommended Resource:", resource)
    print("Learning URL:", url)
    
# 4. Career Plan Retrieval
plan_query = """
PREFIX career: <https://example.org/cognipath/career#>

SELECT ?student ?goal ?activity ?opportunity ?duration
WHERE {
    ?student career:hasCareerGoal ?goal .
    ?student career:hasCareerPlan ?plan .
    ?plan career:achievesGoal ?goal .
    ?plan career:includesActivity ?activity .
    ?activity career:targetsOpportunity ?opportunity .
    ?activity career:durationMinutes ?duration .
}
"""

print("\nCareer Plan:")

for row in graph.query(plan_query):
    print("Student:", row.student.split("#")[-1])
    print("Career Goal:", row.goal.split("#")[-1])
    print("Activity:", row.activity.split("#")[-1])
    print("Target Opportunity:", row.opportunity.split("#")[-1])
    print("Duration:", row.duration, "minutes")

# 5. Automatic Career Activity Suggestions

def generate_career_activities(graph):
    query = """
    PREFIX career: <https://example.org/cognipath/career#>

    SELECT DISTINCT ?opportunity ?skill ?url
    WHERE {
        ?opportunity career:requiresSkill ?skill .

        FILTER NOT EXISTS {
            career:ElhamPournouri career:hasSkill ?skill .
        }

        OPTIONAL {
            ?resource career:helpsLearnSkill ?skill .
            ?resource career:resourceURL ?url .
        }
    }
    """

    activities = []

    for row in graph.query(query):
        skill = row.skill.split("#")[-1]
        opportunity = row.opportunity.split("#")[-1]

        activity = {
            "name": f"Learn {skill}",
            "target_opportunity": opportunity,
            "learning_url": str(row.url) if row.url else None,
            "estimated_duration_minutes": 180
        }

        activities.append(activity)

    return activities


print("\nAutomatically Generated Career Activities:")

activities = generate_career_activities(graph)

for activity in activities:
    print(activity)




# Prepare output for Planner Agent
career_output = {
    "agent": "CareerAgent",
    "student": "ElhamPournouri",
    "goal": "GetAIInternship",
    "activities": activities
}

# Save as JSON
with open("career_plan.json", "w", encoding="utf-8") as file:
    json.dump(career_output, file, indent=4, ensure_ascii=False)

print("\nCareer Plan JSON generated successfully!")
