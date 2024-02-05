import sys
import os
import json
import requests
import paramiko
import dotenv
from signal import signal, SIGINT


from util import init_args, show_table
from util import find_lab_name, handler
from util import get_lab_lists, get_lab_nodes
from util import show_users, show_node_interfaces
from util import select_node_interface
from util import is_node_id, get_linux_interfaces
from util import get_lab_file, update_lab_file
from util import create_network, connect_node_to_network
from util import connect_to_eve

if __name__ == "__main__":
    dotenv.load_dotenv()
    eve_server_ip = os.environ.get("eve_server_ip")
    eve_server_user = os.environ.get("eve_server_user")
    eve_server_password = os.environ.get("eve_server_password")
    http_user = os.environ.get("http_user")
    http_password = os.environ.get("http_password")
    eve_url = f"http://{eve_server_ip}/api"

    signal(SIGINT, handler)

    # login to eve api server as admin
    session = connect_to_eve(eve_url=eve_url, http_user=http_user, http_password=http_password)

    args = init_args().parse_args()
    
    lab_lists = get_lab_lists(session, eve_url)
    # show all labs using -L
    if args.lab_list:
        show_table({"List of Labs": lab_lists})
        sys.exit(0)

    # show all users using -U
    if args.users_list:
        show_users(session, eve_url)
        sys.exit()

    # get current loged-in user ID
    response = session.get(f"{eve_url}/auth")
    user_id = response.json()["data"]["tenant"]

    if args.current_lab:
        current_lab = args.current_lab
    else:
        current_lab = input("Please insert lab id: ")
    # find lab in question
    current_lab = find_lab_name(lab_lists, current_lab)

    # current_lab = {'filename': 'test.unl', 'id': '2221f8a3-c299-40f2-b913-a202099d3a15', 'name': 'test', 'path': '/test.unl'}
    lab_path = current_lab["path"].replace(" ", "%20")
    lab_file_name = current_lab["filename"]

    # get all nodes in current lab
    all_nodes = get_lab_nodes(session, eve_url, lab_path)

    # get list of lab networks
    response = session.get(f"{eve_url}/labs/{lab_path}/networks")
    lab_networks = response.json()["data"]
    if lab_networks:
        for _, network in lab_networks.items():
            if network["visibility"] == 1:
                all_nodes.append({
                    "id": f"net{network['id']}",
                    "name": network["name"],
                    "status": "passive",
                    "type": network["type"], 
                    "ethernet": str(network["count"])
                })

    # show all all nodes table
    if not all_nodes:
        print("[    Info  ] ==> there is no node in the LAB")
        sys.exit(1)
    
    if args.all_nodes:
        show_table({"Nodes List": all_nodes})
        sys.exit(0)


    # get list of lab links
    response = session.get(f"{eve_url}/labs/{lab_path}/links")
    # {"ethernet":{"1":"Net-7750SR1iface_1"},"serial":[]}
    all_links = response.json()["data"]

    if args.node_id:
        if node:= is_node_id(args.node_id, all_nodes):
            show_node_interfaces(session, eve_url, lab_path, node)
            sys.exit()

#  ssh connect to eve-ng
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(eve_server_ip, username=eve_server_user, password=eve_server_password, timeout=1.0)
    except paramiko.AuthenticationException as e:
        print(f"[    Error ]==> {e}")
        sys.exit(1)
    except:
        print(f"[    Error ]==> Could not open ssh connection to eve-ng server {eve_server_ip}")
        sys.exit(1)


    print("[    Info  ] ==> Insert Information for Node A and B")
    node_a, node_a_intf, node_a_type = select_node_interface(session=session, eve_url=eve_url, lab_path=lab_path, device="A", all_nodes=all_nodes)
    # check if interface is not connected
    if node_a_intf["connected"] == "True":
        print("[    Error ] ==> selected Interface is connected already.")
        sys.exit(1)
    node_b, node_b_intf, node_b_type = select_node_interface(session=session, eve_url=eve_url, lab_path=lab_path, device="B", all_nodes=all_nodes)
    # check if interface is not connected
    if node_b_intf["connected"] == "True":
        print("[    Error ] ==> selected Interface is connected already.")
        sys.exit(1)

    if node_a_type == "node" and node_b_type == "node":
        linux_intf_a = f"vunl{user_id}_{node_a['id']}_{node_a_intf['id']}"
        linux_intf_b = f"vunl{user_id}_{node_b['id']}_{node_b_intf['id']}"
        print(f"[    Info  ] ==> NOde A interface name on Linux = {linux_intf_a}")
        print(f"[    Info  ] ==> NOde B interface name on Linux = {linux_intf_b}")

        # get all interfaces from eve-ng server
        linux_interfaces = get_linux_interfaces(client)

        # get last bridge id
        if lab_networks:
            networks = []
            for item in lab_networks:
                networks.append(int(item))
            networks.sort()
            network_id = networks[-1] + 1
        else:
            network_id = 1
        bridge_name = f"vnet{ user_id }_{network_id}"

        print(f"[    Info  ] ==> Bridge name on Linux = {bridge_name}")


        # read lab file
        lab_file = get_lab_file(client=client, lab_file_name=lab_file_name)

        if "networks" in lab_file["lab"]["topology"]:
            lab_networks = lab_file["lab"]["topology"]["networks"]
        else:
            lab_file["lab"]["topology"]["networks"] = {}
            lab_networks = lab_file["lab"]["topology"]["networks"]
        lab_nodes = lab_file["lab"]["topology"]["nodes"]

        
        create_network(lab_networks, network_id, f'Net-{node_a["name"]}iface_{node_a_intf["id"]}')
        connect_node_to_network(lab_nodes, node_a, node_a_intf, network_id)
        connect_node_to_network(lab_nodes, node_b, node_b_intf, network_id)

        print("[    Info  ] ==> Update lab file")
        update_lab_file(client, lab_file_name, lab_file)

        print("[    Info  ] ==> create Linux bridge interface")
        _stdin, _stdout, _stderr = client.exec_command(f"ip link add {bridge_name} mtu 9000 type bridge")
        _stdin, _stdout, _stderr = client.exec_command(f"ip link set {bridge_name} up")
        print("[    Info  ] ==> connect node interfaces to bridge")
        if node_a["status"] == "ON":
            _stdin, _stdout, _stderr = client.exec_command(f"ip link set {linux_intf_a} master {bridge_name}")
        if node_b["status"] == "ON":
            _stdin, _stdout, _stderr = client.exec_command(f"ip link set {linux_intf_b} master {bridge_name}")


        print("[    Info  ] ==> Close SSH connection")
        client.close()
        print("[    Info  ] ==> Close HTTP connection")
        session.close()
        del client, _stdin, _stdout, _stderr

    elif node_a_type == "net" and node_b_type == "net":
        print("[    Error ] ==> connot connect Bridge to Bridge")
        sys.exit(1)

    elif node_a_type == "net" or node_b_type == "net":
        if node_a_type == "node":
            linux_intf = f"vunl{user_id}_{node_a['id']}_{node_a_intf['id']}"
            node = node_a
            node_intf = node_a_intf
            network_id = node_b["id"].split("net")[1]
            network = node_b
        else:
            linux_intf = f"vunl{user_id}_{node_b['id']}_{node_b_intf['id']}"
            node = node_b
            node_intf = node_b_intf
            network_id = node_a["id"].split("net")[1]
            network = node_a
        
        print(f"[    Info  ] ==> Node interface name on Linux = {linux_intf}")
        linux_interfaces = get_linux_interfaces(client)

        lab_file = get_lab_file(client=client, lab_name=lab_file_name)

        if "networks" in lab_file["lab"]["topology"]:
            lab_networks = lab_file["lab"]["topology"]["networks"]
        else:
            lab_file["lab"]["topology"]["networks"] = {}
            lab_networks = lab_file["lab"]["topology"]["networks"]
        lab_nodes = lab_file["lab"]["topology"]["nodes"]
        
        connect_node_to_network(lab_nodes, node, node_intf, network_id)

        update_lab_file(client, lab_file_name, lab_file)

        if network["type"] == "bridge":
            bridge_name = f"vnet{user_id}_{network_id}"
        else:
            bridge_name = network["type"]
        print(f"[    Info  ] ==> Bridge name on Linux = {bridge_name}")

        # check if bridge is exists 
        bridge = list(filter(lambda x: x["ifname"] == bridge_name, linux_interfaces))
        if node["status"] == "ON":
            if not bridge:
                _stdin, _stdout, _stderr = client.exec_command(f"ip link add {bridge_name} mtu 9000 type bridge")
                _stdin, _stdout, _stderr = client.exec_command(f"ip link set {bridge_name} up")            
            _stdin, _stdout, _stderr = client.exec_command(f"ip link set {linux_intf} master {bridge_name}")

        print("[    Info  ] ==> Close SSH connection")
        client.close()
        print("[    Info  ] ==> Close HTTP connection")
        session.close()
        del client, _stdin, _stdout, _stderr
