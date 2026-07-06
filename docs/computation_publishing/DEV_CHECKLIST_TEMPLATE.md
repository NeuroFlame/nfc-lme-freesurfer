# Technical Requirements Checklist for Dev Team Approval  

To gain approval from the development team, ensure the computation module meets the following technical requirements.  

## **Successful Execution**  
- [ ] The module runs successfully with **three or more sites** on the public platform using the provided test data.

## **Computation Description Document**  
Provide a clear and comprehensive document covering the following:  
- [ ] **Algorithm Description** – Explanation of the methodology used.  
- [ ] **Limitations** – Any constraints or known issues with the algorithm.  
- [ ] **Input Data Specification**:  
   - [ ] Structure of the **data directory**.  
   - [ ] Specification for **`parameters.json`**.  
- [ ] **Output Format Description** – Clear definition of expected outputs.  
- [ ] **Minimum Hardware & Space Requirements** – System requirements for execution.
      Craete a log of how many subjects are in each site along with peak RAM usage.
      To track RAM usage, go to docker dashboard, to the specific container and under the 'stats' tab you see RAM usage.
      This info. needs to be included in the compoutation description. Example below:  
      Number of Subjects:RAM Needed (GB)  
            1,824        : 26.62544646  
            327         	: 6.895502383  
            188         	: 4.462923564  
- [ ] **Basic Dataset Validator** – A tool or script to validate input data format.  

## **GitHub Repository**  
Ensure the module is properly hosted and documented:  
- [ ] The module is in a **publicly accessible repository**.  
- [ ] The repository includes:  
   - [ ] A **buildable, working image**.  
   - [ ] **Test data** for validation (**3 or more sites**).  
   - [ ] The **computation description document**.  

