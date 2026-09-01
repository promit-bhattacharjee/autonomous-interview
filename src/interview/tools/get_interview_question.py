from langchain import tool
# pyrefly: ignore [missing-import]
from src.interview.state import InitialQuestionFileFormat

@tool
def get_initial_question(type:str):
    """
    this tool will get the raw file and extract the text from the file 
    """