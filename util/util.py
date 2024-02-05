
import sys
import argparse
import json
import requests

import xmltodict
from rich.console import Console
from rich.table import Table



def handler(signal_received, frame):
    # Handle any cleanup here
    print('\nSIGINT or CTRL-C detected. Exiting gracefully')
    exit(0)

def connect_to_eve(eve_url, http_user, http_password):
    session = requests.session()
    data = {"username":http_user,"password":http_password}
    response = session.post(f"{eve_url}/auth/login", data=json.dumps(data))
    if not response.ok:
        print(response.text)
        print("[    Error ] ==> Cannot connect to eve-ng api server. please check if the server information is correct.")
        print(f"[    Info  ] ==> {eve_url =}")
        print(f"[    Info  ] ==> {http_user =}")
        print(f"[    Info  ] ==> {http_password =}")
        sys.exit(1)
    
    return session


def get_lab_lists(session, eve_url):
    # get all files and folder from eve-ng api
    def get_folder_data(folder):
        nonlocal session
        path = folder["path"]
        response = session.get(f"{eve_url}/folders{path}")
        return response.json()["data"]["folders"], response.json()["data"]["labs"]
    response = session.get(f"{eve_url}/folders/")
    list_of_files = response.json()["data"]
    labs= list_of_files["labs"]
    folders: list = list_of_files["folders"]
    while folders:
        folder = folders.pop()
        if folder["name"] == "..":
            continue
        dir, lab = get_folder_data(folder)
        labs = labs + lab
        folders = folders + dir
    result = []
    for lab in labs:
        path = lab["path"]
        response = session.get(f"{eve_url}/labs{path}")
        data = response.json()["data"]
        data["path"] = path
        for item in ["author", "lock", "scripttimeout",
                     "version","body","description"]:
            data.pop(item)
        result.append(data)
    return result

def get_lab_nodes(session, eve_url, lab_path):
    # get lab nodes
    response = session.get(f"{eve_url}/labs{lab_path}/nodes")
    nodes = response.json()["data"]
    result = []
    if nodes:
        for _, node in nodes.items():
            for item in ["console", "delay", "left", "icon", "image",
                        "ram", "template", "top", "url", "config_list",
                        "config", "cpu", "uuid","nvram", "serial"]:
                node.pop(item, None)
            node["id"] = str(node["id"])
            node["ethernet"] = str(node["ethernet"])
            node["status"] = "OFF" if node["status"] == 0 else "ON"
            result.append(node)
    return  result

def show_users(session, eve_url):
    # show all eve-ng users
    response = session.get(f"{eve_url}/users/")
    data = response.json()["data"]
    result = []
    for _, user in data.items():
        for item in ["expiration", "session", "pod", "pexpiration"]:
            user.pop(item)
        result.append(user)
    show_table({"List of all users": result})


def select_node_interface(session, eve_url, lab_path, device, all_nodes):
    # ask user to select a node fro a lab
    show_table({"Nodes List": all_nodes})
    node = input(f"Please Insert Node {device} id from above table: ")
    node = is_node_id(node, all_nodes)

    if node["id"].startswith("net"):
        return node, None, "net"

    node_interfaces = show_node_interfaces(session, eve_url, lab_path, node)
    node_intf = input("Please Insert port name or id from above Table: ")
    node_intf = list(filter(lambda x: x["id"] == node_intf or x["name"] == node_intf, node_interfaces))
    if node_intf:
        return node, node_intf[0], "node"
    else:
        print("[    Error ] ==> selected Interface is not exist")
        sys.exit(1)


def show_node_interfaces(session, eve_url, lab_path, node):
    # show node Interfaces information
    global all_nodes
    response = session.get(f"{eve_url}/labs/{lab_path}/nodes/{node["id"]}/interfaces")
    data = response.json()["data"]
    if data["sort"] in ["qemu", "vpcs"]:
        for id, link in enumerate(data["ethernet"]):
            link["network_id"] = str(link["network_id"])
            link["connected"] = "True" if int(link["network_id"]) != 0 else "False"
            link["id"] = str(id)
    elif data["sort"] == "iol":
        tmp = []
        for id, link in data["ethernet"].items():
            link["network_id"] = str(link["network_id"])
            link["connected"] = "True" if int(link["network_id"]) != 0 else "False"
            link["id"] = str(id)
            tmp.append(link)
        data["ethernet"] = tmp
    show_table({f"List of interfaces for node_name={node['name']} && node_id={node['id']}": data["ethernet"]})
    return data["ethernet"]


def show_table(table_data):
    # show information as a table
    table = Table(title=list(table_data.keys())[0], show_lines=True)
    for _, rows in table_data.items():
        for cell in rows[0].keys():
            table.add_column(cell, justify="left")
    for _, rows in table_data.items():
        for id, row in enumerate(rows):
            table.add_row(*tuple(row.values()))
    console = Console()
    console.print(table)


def find_lab_name(lab_lists, current_lab):
    # find lab base on name or ID
    lab = list(filter(lambda x: current_lab in x["name"] or current_lab in x["id"], lab_lists))
    if len(lab) > 1:
        print(f"[    Error ] ==> We found more than one lab with same {current_lab}.\n"
              "[    Info  ] ==> Please check below table and provide more specfic information")
        show_table({"Dublicate labs": lab})
        sys.exit()
    elif len(lab) == 0:
        print(f"[   Error ] ==> We couldn't find {current_lab} in below lists")
        show_table({"List of Labs":lab_lists})
        sys.exit()
    return lab[0]

def is_node_id(node_id, all_nodes):
    # check if user input is a node
    if node := list(filter(lambda x: x["id"] == node_id, all_nodes)):
        return node[0]
    else:
        print("[    Error ] ==> selected Node ID is not avalible.")
        print("[    Info  ] ==> below table is the list of avalible Nodes.")
        if all_nodes:
            show_table({"Nodes List": all_nodes})
        sys.exit(1)

def get_linux_interfaces(client) -> json.loads:
    # get linux server interfaces as json 
    _stdin, _stdout,_stderr = client.exec_command("ip --json add")
    linux_interfaces = _stdout.read().decode()
    return json.loads(linux_interfaces)

def get_lab_file(client, lab_file_name) -> xmltodict.parse:
    # read the lab file and convert it to dict
    _stdin, _stdout,_stderr = client.exec_command(f"cat /opt/unetlab/labs/{lab_file_name}")
    lab_file = _stdout.read().decode()
    return xmltodict.parse(lab_file)

def update_lab_file(client, lab_file_name, lab_file):
    # write lab file with new information
    new_unl = xmltodict.unparse(lab_file, pretty=True)
    ftp = client.open_sftp()
    file = ftp.file(f"/opt/unetlab/labs/{lab_file_name}","w")
    file.write(new_unl)
    file.flush()
    file.close()
    ftp.close()

def create_network(lab_networks, network_id, network_name):
    # this function will edit the lab file and add a new network
    if not lab_networks:
        lab_networks["network"] = {'@id': network_id, '@type': 'bridge', '@name': network_name, '@left': '504', '@top': '289', '@visibility': '0'}
    elif isinstance(lab_networks["network"],dict):
        lab_networks["network"] = [lab_networks["network"], {'@id': network_id, '@type': 'bridge', '@name': network_name, '@left': '504', '@top': '289', '@visibility': '0'}]
    elif isinstance(lab_networks["network"], list):
        lab_networks["network"].append({'@id': network_id, '@type': 'bridge', '@name': network_name, '@left': '504', '@top': '289', '@visibility': '0'})

def connect_node_to_network(lab_nodes, node, node_intf, network_id):
    # this function will edit the lab file and connect node to a network
    for xml_node in lab_nodes["node"]:
        if xml_node["@id"] == str(node["id"]):
            if not xml_node.get("interface", None):
                xml_node["interface"] = {'@id': node_intf["id"], '@name': node_intf["name"], '@type': 'ethernet', '@network_id': network_id}
            elif isinstance(xml_node["interface"],dict):
                xml_node["interface"] = [xml_node["interface"], {'@id': node_intf["id"], '@name': node_intf["name"], '@type': 'ethernet', '@network_id': network_id}]
            elif isinstance(xml_node["interface"], list):
                xml_node["interface"].append({'@id': node_intf["id"], '@name': node_intf["name"], '@type': 'ethernet', '@network_id': network_id})


def init_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTIONS]",
        description="EVE-NG Comminuty tools",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{parser.prog} version 0.0.1"
    )
    gr_eve = parser.add_argument_group('EVE-NG info')
    gr_eve.add_argument(
        "-L",
        "--lab-list",
        required=False,
        action="store_true",
        help="Show list of avalible lab in eve-ng.",
    )
    gr_eve.add_argument(
        "-U",
        "--users-list",
        required=False,
        action="store_true",
        help="Show list of all users in eve-ng.",
    )
    gr_lab = parser.add_argument_group('EVE-NG LAB Info')
    gr_lab.add_argument(
        "-C",
        "--current-lab",
        required=False,
        help="choose lab based on Lab-Name or Lab-ID. This is the LAB that user would like to work on.",
    )
    gr_node = parser.add_argument_group('EVE-NG node information on chosen LAB')
    gr_node.add_argument(
        "-A",
        "--all-nodes",
        required=False,
        action="store_true",
        help="Show list of all Nodes on chosen lab.",
    )
    gr_node.add_argument(
        "-N",
        "--node-id",
        required=False,
        help="Show list of all interfaces for provided node ID.",
    )
    return parser
