import streamlit as st
import io
import PyPDF2
from pydantic import BaseModel, Field
from typing import TypedDict, Annotated
import operator
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

# Load env
load_dotenv()

# LLM model
model = ChatOpenAI(model="gpt-4o-mini")

# Pydantic structure
class EvalSchema(BaseModel):
    feedback: str = Field(description="Detailed feedback")
    score: int = Field(description="Score out of 10", ge=0, le=10)

StructuredModel = model.with_structured_output(EvalSchema)

# Extract PDF text function
def extract_pdf_text(uploaded_file):
    pdf_reader = PyPDF2.PdfReader(uploaded_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text.strip()

# STATE
class CVState(TypedDict):
    cv_text: str
    overall_feedback: str
    education_feedback: str
    skills_feedback: str
    individual_scores: Annotated[list[int], operator.add]
    avg_score: float

# --- NODE 1: Overall CV Quality ---
def evaluate_overall(state: CVState):
    prompt = f"Evaluate the overall quality of this CV. Give feedback + score (0–10):\n\n{state['cv_text']}"
    out = StructuredModel.invoke(prompt)
    return {"overall_feedback": out.feedback, "individual_scores": [out.score]}

# --- NODE 2: Education Evaluation ---
def evaluate_education(state: CVState):
    prompt = f"Evaluate the Education section of this CV. Give feedback + score (0–10):\n\n{state['cv_text']}"
    out = StructuredModel.invoke(prompt)
    return {"education_feedback": out.feedback, "individual_scores": [out.score]}

# --- NODE 3: Skills Evaluation ---
def evaluate_skills(state: CVState):
    prompt = f"Evaluate the Skills section of this CV. Give feedback + score (0–10):\n\n{state['cv_text']}"
    out = StructuredModel.invoke(prompt)
    return {"skills_feedback": out.feedback, "individual_scores": [out.score]}

# --- FINAL NODE ---
def final_summary(state: CVState):

    avg_score = sum(state["individual_scores"]) / len(state["individual_scores"])

    # Recommendation if score < 7
    if avg_score < 7:
        improvement_prompt = f"""
The following CV scored low ({avg_score}/10). 
Give improvement suggestions based on feedback below:

Overall: {state['overall_feedback']}
Education: {state['education_feedback']}
Skills: {state['skills_feedback']}
"""
        improvement = model.invoke(improvement_prompt).content
    else:
        improvement = "Good CV. No major improvements required."

    return {"avg_score": avg_score, "overall_feedback": improvement}


# ---- BUILD LANGGRAPH WORKFLOW ----
graph = StateGraph(CVState)

graph.add_node("overall", evaluate_overall)
graph.add_node("education", evaluate_education)
graph.add_node("skills", evaluate_skills)
graph.add_node("final", final_summary)

# Parallel execution
graph.add_edge(START, "overall")
graph.add_edge(START, "education")
graph.add_edge(START, "skills")

# Reduce into final
graph.add_edge("overall", "final")
graph.add_edge("education", "final")
graph.add_edge("skills", "final")

graph.add_edge("final", END)

workflow = graph.compile()


# ------------- STREAMLIT UI -------------
st.title("📄 AI CV Analyzer")
st.write("Upload your CV (PDF), and the AI will analyze it.")

uploaded_file = st.file_uploader("Upload CV PDF", type=["pdf"])

if uploaded_file:
    cv_text = extract_pdf_text(uploaded_file)

    st.subheader("Extracted CV Text:")
    st.text_area("CV Content", cv_text, height=250)

    if st.button("Analyze CV"):
        with st.spinner("Analyzing..."):
            result = workflow.invoke({"cv_text": cv_text})

        st.success("Analysis Completed!")

        st.subheader("📌 Final Feedback")
        st.write(result["overall_feedback"])

        st.subheader("📊 Scores")
        st.write(f"**Average Score:** {result['avg_score']}/10")

        st.subheader("📝 Detailed Scores")
        st.write(f"Overall Quality Score: {result['individual_scores'][0]}")
        st.write(f"Education Score: {result['individual_scores'][1]}")
        st.write(f"Skills Score: {result['individual_scores'][2]}")

