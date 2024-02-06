
import sys
import argparse
import json
import requests

import paramiko

import xmltodict
from rich.console import Console
from rich.table import Table


class EVE_HTTP():
    def __init__(self, eve_url, http_user, http_password) -> None:
        self.url = eve_url
        self.user = http_user
        self.password = http_password
        self.lab_name = ""

    def connect(self):
        self.session = requests.session()
        data = {"username":self.user,"password":self.password}
        response = self.session.post(f"{self.url}/auth/login", data=json.dumps(data))
        if not response.ok:
            return response
        else:
            response = self.session.get(f"{self.url}/auth")
            self.user_id = response.json()["data"]["tenant"]
            return True

    def get_lab_lists(self):
        # get all files and folder from eve-ng api
        def get_folder_data(folder):
            path = folder["path"]
            response = self.session.get(f"{self.url}/folders{path}")
            return response.json()["data"]["folders"], response.json()["data"]["labs"]
        response = self.session.get(f"{self.url}/folders/")
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
            response = self.session.get(f"{self.url}/labs{path}")
            data = response.json()["data"]
            data["path"] = path
            for item in ["author", "lock", "scripttimeout",
                        "version","body","description"]:
                data.pop(item)
            result.append(data)
        self.lab_lists = result

    def get_users(self):
        # show all eve-ng users
        response = self.session.get(f"{self.url}/users/")
        data = response.json()["data"]
        result = []
        for _, user in data.items():
            for item in ["expiration", "session", "pod", "pexpiration"]:
                user.pop(item, None)
            result.append(user)
        return result

    def find_lab_name(self):
        # find lab base on name or ID
        lab = list(filter(lambda x: self.lab_name in x["name"] or self.lab_name in x["id"], self.lab_lists))
        if len(lab) > 1:
            print(f"[    Error ] ==> We found more than one lab with same {self.lab_name} information.\n")
            return False
        elif len(lab) == 0:
            print(f"[   Error ] ==> We couldn't find {self.lab_name} in below lists")
            return False
        self.lab = lab[0]
        self.lab_name = self.lab["filename"]
        self.lab_path = self.lab["path"].replace(" ", "%20")
        return self.lab

    def get_lab_networks(self):
        response = self.session.get(f"{self.url}/labs/{self.lab_path}/networks")
        self.lab_networks = response.json()["data"]

    def get_lab_nodes(self):
        # get lab nodes
        response = self.session.get(f"{self.url}/labs{self.lab_path}/nodes")
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
        self.lab_nodes = result

    def is_node_id(self, node_id):
        if node := list(filter(lambda x: x["id"] == node_id, self.lab_nodes)):
            return node[0]
        else:
            return False

    def get_node_interfaces(self, node):
        response = self.session.get(f"{self.url}/labs/{self.lab_path}/nodes/{node["id"]}/interfaces")
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
        return data["ethernet"]

    def select_node_interface(self, device= ""):
        # ask user to select a node fro a lab
        show_table({"Nodes List": self.lab_nodes})
        node = input(f"Please Insert Node {device} id from above table: ")
        node = self.is_node_id(node)
        if node == False:
            print("[    Error ] ==> Input ID is not correct")
            sys.exit(1)

        if node["id"].startswith("net"):
            return node, None, "net"

        node_interfaces = self.get_node_interfaces(node)
        show_table({f"Interfaces for {node['name']}": node_interfaces})
        node_intf = input("Please Insert port name or id from above Table: ")
        node_intf = list(filter(lambda x: x["id"] == node_intf or x["name"] == node_intf, node_interfaces))
        if node_intf:
            return node, node_intf[0], "node"
        else:
            print("[    Error ] ==> selected Interface is not exist")
            sys.exit(1)

class EVE_SSH():
    def __init__(self, ip, user, password) -> None:
        self.ip = ip
        self.user = user
        self.password = password
    
    def connect(self):
        self.client =  paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.client.connect(self.ip, username=self.user, password=self.password, timeout=1.0)
        except paramiko.AuthenticationException as e:
            print(f"[    Error ]==> {e}")
            sys.exit(1)
        except:
            print(f"[    Error ]==> Could not open ssh connection to eve-ng server {self.ip}")
            sys.exit(1)

    def send_command(self, cmd):
         _stdin, _stdout, _stderr = self.client.exec_command(cmd)


    def get_lab_file(self, lab_info) -> xmltodict.parse:
        # read the lab file and convert it to dict
        path = lab_info["path"]
        _stdin, _stdout,_stderr = self.client.exec_command(f"cat '/opt/unetlab/labs/{path}'")
        lab_file = _stdout.read().decode()
        return xmltodict.parse(lab_file)

    def update_lab_file(self, lab_info, file_data):
        path = lab_info["path"]
        new_unl = xmltodict.unparse(file_data, pretty=True)
        ftp = self.client.open_sftp()
        file = ftp.file(f"/opt/unetlab/labs/{path}","w")
        file.write(new_unl)
        file.flush()
        file.close()
        ftp.close()

    def get_linux_interfaces(self) -> json.loads:
        # get linux server interfaces as json 
        _stdin, _stdout,_stderr = self.client.exec_command("ip --json add")
        linux_interfaces = _stdout.read().decode()
        return json.loads(linux_interfaces)

def handler(signal_received, frame):
    # Handle any cleanup here
    print('\nSIGINT or CTRL-C detected. Exiting gracefully')
    exit(0)


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
