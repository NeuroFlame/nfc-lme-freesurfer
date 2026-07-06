# Neuroflame Computation Interface Document

These details explain how Neuroflame manages container initialization, provisioning, and file mounting. Computation authors do not need to interact with these components, but understanding them can provide helpful context.

## The System Folder

- **Purpose:**  
  The `/system` folder encapsulates the details of container management and file mounting conventions.

- **Contents:**  
  It contains three entry point scripts that run when a container is launched:
  - `entry_central.py` – Launches the central federated client.
  - `entry_edge.py` – Launches the edge federated client.
  - `entry_provision.py` – Executes the provisioning step before a federated run starts.

## Provisioning Process

Provisioning generates secure startup packages that allow sites to join a federated network.

### Overview

- **StartupKits and RunKits:**  
  - **StartupKits:** Created by NVFLARE commands during the provisioning step.
  - **RunKits:** NeuroFlame wraps these startupKits into runKits. For the central node, runKits additionally include `parameters.json` for loading into NVFLARE’s controller context.
  
- **Process Flow:**  
  1. **Container Launch:**  
     Neuroflame starts a container using `entry_provision.py`.
  2. **File Operations & Command Execution:**  
     Within the container, file operations and NVFLARE commands generate the startupKits.
  3. **Composition:**  
     The startupKits are wrapped into runKits.
  4. **Distribution:**  
     Once the container exits, Neuroflame zips and distributes the runKits to each site and the central node.
  5. **Client Startup:**  
     Edge and central federated clients receive an event to start their nodes using `entry_edge.py` and `entry_central.py` respectively.

### Provisioning Input

The provisioning container consumes a JSON file named `provision_input.json` with the following structure:

```json
{
    "user_ids": ["list of user IDs"],
    "computation_parameters": "string containing computation parameters as a stringified json object",
    "fed_learn_port": 1234,
    "admin_port": 5678,
    "host_identifier": "IP or hostname"
}
```

- **user_ids:** Unique IDs for each active site.
- **computation_parameters:** A JSON object (as a string) defined by the consortium leader.
- **fed_learn_port:** The port used for client connections.
- **admin_port:** The port where the admin component is hosted.
- **host_identifier:** The IP address or hostname for the central node.

## Mounting Conventions

Neuroflame maps host directories into the containers according to the following conventions:

| **Component**              | **Host Directory**                   | **Container Mount Point**  | **Purpose**                                          |
|----------------------------|--------------------------------------|----------------------------|------------------------------------------------------|
| **Provisioning Container** | Run-specific directory (e.g., `run`) | `/provisioning/`           | Temporary workspace for provisioning operations; includes `provision_input.json` written before launch. |
| **Edge Client**            | Run-specific directory/runKit        | `/workspace/runKit`        | Contains configuration files (runKits) for the computation run. |
|                            | Data directory                       | `/workspace/data`          | Read-only site-specific input data.                |
|                            | Output directory                     | `/workspace/output`        | For computation outputs (results, logs, errors).     |
| **Central Client**         | Run-specific directory/runKit        | `/workspace/runKit`        | Contains configuration files including `parameters.json`. |

> **Directory Summary:**  
> - **`/workspace/data`:** Read-only site-specific input data for the computation.  
> - **`/workspace/output`:** Computation outputs, including results, logs, and error reports.  
> - **`/workspace/runKit`:** Configuration files for the computation run, including `parameters.json` (central node only).  
> - **`/provisioning/`:** Used exclusively during the provisioning process.

---

- **System Folder:** Manages container entry point scripts.
- **Provisioning:** Wraps NVFLARE startupKits into NeuroFlame runKits and distributes them across the network.
- **Mounting Conventions:** Refer to the table above for a clear mapping of host directories to container paths.

--- 

This document provides a concise overview of the Neuroflame computation interface. While computation authors don’t need to interact with these components, understanding them offers insight into how NVFLARE apps are deployed and managed within the Neuroflame ecosystem.