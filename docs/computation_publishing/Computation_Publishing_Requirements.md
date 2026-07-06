# Computation Module Publishing Requirements

## Technical Requirements for Dev Team Approval

To gain approval from the development team, the computation module must meet the following technical requirements:

- **Successful Execution**
  - The module must run successfully with three or more sites on the public platform using the provided test data.

- **Computation Description Document**
  - A clear and comprehensive document must be provided, including:
    - **Algorithm Description** – Explanation of the methodology used.
    - **Limitations** – Any constraints or known issues with the algorithm.
    - **Input Data Specification**:
      - Structure of the **data directory**.
      - Specification for **`parameters.json`**.
    - **Output Format Description** – Clear definition of expected outputs.
    - **Minimum Hardware & Space Requirements** – System requirements for execution.
    - **Basic Dataset Validator** – A tool or script to validate input data format.

- **GitHub Repository**
  - The module must be hosted in a **publicly accessible repository**.
  - The repository should include:
    - A **buildable, working image**.
    - **Test data** for validation. (3 or more sites)
    - The **computation description document**.

---

## PI Approval Requirements

Principal Investigators (PIs) are responsible for defining and enforcing additional requirements specific to their computation module. In addition to the general technical requirements, PIs must:

- Document their specific requirements within the computation module’s repository.
- Ensure the module meets the following suggested criteria:

  - **Accuracy & Meaningfulness of Results**
    - Verify that the module produces **valid and meaningful** computational results.
  
  - **Compatibility with Intended Datasets**
    - Confirm that the **data format specification** aligns with intended use cases.
    - Test against **multiple dataset variations** conforming to the specified format.
    - Utilize **real-world datasets** as examples.

  - **Dataset Validator Approval**
    - Approve the basic dataset validator to ensure correct input data formatting.

  - **Additional PI-Specific Requirements**
    - Define any **module-specific** criteria beyond the generic requirements.

---

## **Tracking and Documenting Validation Checks**  

Each computation module repository must maintain version-controlled checklists to track approval status and validation progress. The following checklist files are located in the same directory as this document and should be maintained within the repository:  

- **[DEV_CHECKLIST_TEMPLATE.md](./DEV_CHECKLIST_TEMPLATE.md)**  
  - Tracks **technical requirements** for development team approval.  
  - Documents progress on successful execution, repository setup, and required documentation.  
  - Should be regularly updated with completion status and any pending issues.  

- **[PI_CHECKLIST_TEMPLATE.md](./PI_CHECKLIST_TEMPLATE.md)**  
  - Tracks **PI-specific approval requirements** for accuracy, dataset compatibility, and validation.  
  - Allows PIs to document any additional criteria for module acceptance.  

These checklists must be updated as progress is made and committed to version control to maintain a clear history of approvals, pending actions, and validation status.  
