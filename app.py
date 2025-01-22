import requests
from bs4 import BeautifulSoup
import json
import re
import spacy
import language_tool_python
import streamlit as st
from PyDictionary import PyDictionary


import spacy
from spacy.cli import download

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    download("en_core_web_sm")  # Automatically download if not found
    nlp = spacy.load("en_core_web_sm")


# Initialize LanguageTool for grammar corrections
tool = language_tool_python.LanguageTool('en-US')

# Initialize PyDictionary for external dictionary lookup (optional)
dictionary = PyDictionary()

# Load medical definitions from the provided JSON file
def load_medical_definitions(file_path):
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
            definitions = data.get("definitions", [])
            # Validate structure
            if not all(isinstance(item, dict) and "term" in item and "definition" in item for item in definitions):
                raise ValueError("Each definition must be a dictionary containing 'term' and 'definition'.")
            return definitions
    except Exception as e:
        raise RuntimeError(f"Error loading medical definitions: {e}")

# Simplify terms in a text using loaded definitions
def simplify_terms(text, definitions):
    for term in definitions:
        term_lower = term["term"].lower()
        definition = term["definition"]
        text = re.sub(rf"\b{term_lower}\b", definition, text, flags=re.IGNORECASE)
    return text

# Improve grammar and convert text to questions
def improve_question_grammar(text):
    if "individuals" in text.lower():
        text = re.sub(r"\bindividuals\b", "Do you", text, flags=re.IGNORECASE)
    if "diagnosis" in text.lower():
        text = re.sub(r"\bdiagnosis\b", "Have you been diagnosed with", text, flags=re.IGNORECASE)
    text = re.sub(r"have\s(current|severe)\s", "Do you currently have ", text)
    return text

# Correct grammar using LanguageTool
def correct_grammar(text):
    matches = tool.check(text)
    return language_tool_python.utils.correct(text, matches)

# Function to simplify terms using terms loaded from data.json
def simplify_terms_with_dictionary(text, definitions):
    # Ensure definitions is a list of dictionaries containing 'term' and 'definition'
    if not isinstance(definitions, list):
        raise ValueError("The definitions should be a list of dictionaries.")

    # Iterate through the definitions and replace terms in the text
    for term_dict in definitions:
        if isinstance(term_dict, dict) and "term" in term_dict and "definition" in term_dict:
            term_lower = term_dict["term"].lower()  # Case insensitive matching
            if term_lower in text.lower():
                text = re.sub(rf"\b{term_lower}\b", term_dict["definition"], text, flags=re.IGNORECASE)
        else:
            print(f"Invalid format in term dictionary: {term_dict}")
    return text

# Generate survey questions from content
def convert_to_survey_questions_with_nlp(content, definitions):
    lines = re.split(r'\d+\.\s*', content)  # Split by numbered points
    survey_questions = []

    for idx, line in enumerate(lines, start=1):
        line = line.strip()
        if line:
            simplified_line = simplify_terms_with_dictionary(line, definitions)
            improved_line = improve_question_grammar(simplified_line)
            corrected_line = correct_grammar(improved_line)
            question = f"Question {idx}: {corrected_line} (Yes/No)"
            survey_questions.append(question)

    return survey_questions

# Streamlit UI
def main():
    st.title("Medical Trial Survey Generator")

    # Upload JSON file containing medical definitions
    uploaded_file = st.file_uploader("Upload your medical definitions file (JSON)", type=["json"])
    if uploaded_file is not None:
        definitions = json.load(uploaded_file).get("definitions", [])
        
        # Get condition input
        condition = st.text_input("Enter the medical condition (e.g., HIV, Cancer):")

        if st.button("Generate Questions"):
            if condition.strip():
                base_url = "https://unitytrials.org/trials/"
                search_url = f"{base_url}{condition.lower().replace(' ', '-')}"
                st.write(f"Fetching data from: {search_url}")
                
                response = requests.get(search_url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
                    
                    if script_tag:
                        data = json.loads(script_tag.string)
                        study_items = data.get("props", {}).get("pageProps", {}).get("getStudies", {}).get("items", [])
                        if study_items:
                            paths = [item.get("path") for item in study_items if "path" in item]
                            st.write(f"Found {len(paths)} study paths.")
                            
                            choice = st.selectbox("Select a study:", paths)
                            selected_path = choice
                            trial_url = f"https://unitytrials.org{selected_path}"
                            trial_response = requests.get(trial_url)
                            if trial_response.status_code == 200:
                                trial_soup = BeautifulSoup(trial_response.text, "html.parser")
                                participation_criteria_wrapper = trial_soup.find("div", class_="participation__criteria-wrapper")
                                if participation_criteria_wrapper:
                                    participation_criteria_content = participation_criteria_wrapper.get_text(strip=True, separator=" ")
                                    survey_questions = convert_to_survey_questions_with_nlp(participation_criteria_content, definitions)

                                    for question in survey_questions:
                                        st.write(question)
                                else:
                                    st.write("No participation criteria found.")
                            else:
                                st.write(f"Failed to fetch trial page: {trial_url}")
                        else:
                            st.write("No study items found.")
                    else:
                        st.write("Error: Couldn't find study data.")
                else:
                    st.write("Error: Failed to fetch search results page.")
            else:
                st.write("Please enter a valid medical condition.")

if __name__ == "__main__":
    main()
