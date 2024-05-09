import sys
import dotenv
from signal import signal, SIGINT

from util import EVE_HTTP
from util import EVE_SSH
from util import EVE_INFO

from util import init_args
from util import handler
from util import create_network
from util import connect_node_to_network
from util import init_server_info
from util import args_check

if __name__ == "__main__":
    dotenv.load_dotenv()
    eve_info = EVE_INFO()

    init_server_info(eve_info)


    signal(SIGINT, handler)
    args = init_args().parse_args()

    # login to eve api server as admin
    eve_http = EVE_HTTP(eve_url=eve_info.url, http_user=eve_info.http_user, http_password=eve_info.http_pass)

    args_check(args, eve_http)

    if eve_http.lab_networks:
        for _, network in eve_http.lab_networks.items():
            if network["visibility"] == 1:
                eve_http.lab_nodes.append({
                    "id": f"net{network['id']}",
                    "name": network["name"],
                    "status": "passive",
                    "type": network["type"], 
                    "ethernet": str(network["count"])
                })

    eve_ssh = EVE_SSH(ip=eve_info.ip, user=eve_info.server_user, password=eve_info.server_pass)
    eve_ssh.connect()

    print("[    Info  ] ==> Insert Information for Node A and B")
    node_a, node_a_intf, node_a_type = eve_http.select_node_interface(device="A")
    # check if interface is not connected
    if node_a_type != "net" and node_a_intf["connected"] == "True":
        print(f"[    Error ] ==> Interface {node_a_intf['name']} on device {node_a['name']} is connected already.")
        sys.exit(1)
    node_b, node_b_intf, node_b_type = eve_http.select_node_interface(device="B")
    # check if interface is not connected
    if node_b_type != "net" and node_b_intf["connected"] == "True":
        print(f"[    Error ] ==> Interface {node_b_intf['name']} on device {node_b['name']} is connected already.")
        sys.exit(1)

    if node_a_type == "node" and node_b_type == "node":
        linux_intf_a = f"vunl{eve_http.user_id}_{node_a['id']}_{node_a_intf['id']}"
        linux_intf_b = f"vunl{eve_http.user_id}_{node_b['id']}_{node_b_intf['id']}"
        print(f"[    Info  ] ==> NOde A interface name on Linux = {linux_intf_a}")
        print(f"[    Info  ] ==> NOde B interface name on Linux = {linux_intf_b}")

        # get not used bridge id
        if eve_http.lab_networks:
            net_ids = [int(item) for item in eve_http.lab_networks]
            net_ids.sort()
            max = net_ids[-1]
            not_used_ids = []
            for item in range(1, max+1):
                if item not in net_ids:
                    not_used_ids.append(item)
            if not_used_ids:
                network_id = not_used_ids[0]
            else:
                network_id = max + 1
        else:
            network_id = 1
        bridge_name = f"vnet{ eve_http.user_id }_{network_id}"
        print(f"[    Info  ] ==> Bridge name on Linux = {bridge_name}")

        # read lab file
        lab_file = eve_ssh.get_lab_file(lab_info=eve_http.lab)

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
        eve_ssh.update_lab_file(lab_info=eve_http.lab, file_data=lab_file)

        print("[    Info  ] ==> create Linux bridge interface")
        eve_ssh.send_command(f"ip link add {bridge_name} mtu 9000 type bridge")
        eve_ssh.send_command(f"ip link set {bridge_name} up")
        print("[    Info  ] ==> connect node interfaces to bridge")
        if node_a["status"] == "ON":
            eve_ssh.send_command(f"ip link set {linux_intf_a} master {bridge_name}")
        if node_b["status"] == "ON":
            eve_ssh.send_command(f"ip link set {linux_intf_b} master {bridge_name}")


        print("[    Info  ] ==> Close SSH connection")
        eve_ssh.client.close()
        print("[    Info  ] ==> Close HTTP connection")
        eve_http.session.close()


    elif node_a_type == "net" and node_b_type == "net":
        print("[    Error ] ==> cannot connect Bridge to Bridge")
        sys.exit(1)

    elif node_a_type == "net" or node_b_type == "net":
        if node_a_type == "node":
            linux_intf = f"vunl{eve_http.user_id}_{node_a['id']}_{node_a_intf['id']}"
            node = node_a
            node_intf = node_a_intf
            network_id = node_b["id"].split("net")[1]
            network = node_b
        else:
            linux_intf = f"vunl{eve_http.user_id}_{node_b['id']}_{node_b_intf['id']}"
            node = node_b
            node_intf = node_b_intf
            network_id = node_a["id"].split("net")[1]
            network = node_a
        
        print(f"[    Info  ] ==> Node interface name on Linux = {linux_intf}")
        linux_interfaces = eve_ssh.get_linux_interfaces()

        lab_file = eve_ssh.get_lab_file(lab_info=eve_http.lab)

        if "networks" in lab_file["lab"]["topology"]:
            lab_networks = lab_file["lab"]["topology"]["networks"]
        else:
            lab_file["lab"]["topology"]["networks"] = {}
            lab_networks = lab_file["lab"]["topology"]["networks"]
        lab_nodes = lab_file["lab"]["topology"]["nodes"]
        
        connect_node_to_network(lab_nodes, node, node_intf, network_id)

        eve_ssh.update_lab_file(lab_info=eve_http.lab, file_data=lab_file)

        if network["type"] == "bridge":
            bridge_name = f"vnet{eve_http.user_id}_{network_id}"
        else:
            bridge_name = network["type"]
        print(f"[    Info  ] ==> Bridge name on Linux = {bridge_name}")

        # check if bridge is exists 
        bridge = list(filter(lambda x: x["ifname"] == bridge_name, linux_interfaces))
        if node["status"] == "ON":
            if not bridge:
                eve_ssh.send_command(f"ip link add {bridge_name} mtu 9000 type bridge")
                eve_ssh.send_command(f"ip link set {bridge_name} up")            
            eve_ssh.send_command(f"ip link set {linux_intf} master {bridge_name}")

        print("[    Info  ] ==> Close SSH connection")
        eve_ssh.client.close()
        print("[    Info  ] ==> Close HTTP connection")
        eve_http.session.close()

