import socket
from socket import *
# https://docs.python.org/3/library/socket.html
import threading # multi threading: sending and receiving at the same time
# https://www.liujiangblog.com/course/python/79
import sys # for CLI
import os # os.exit()
import time
import json
import queue
import re

'''
UDP Datagram Format
sender_listening_port:
<sender_listening_port>
sender_name:
<sender_name> (uniquely identify an instance, like an id)
msg_type:
<reg_ack/ack/table/grp_msg/pri_msg> (client may receive)
<reg/dereg/create_group/list_groups/join_group/leave_group/list_members/send_group/ack/kick> (server may receive)
message:
<actual message>
'''


def packetFormat(sender_listening_port, sender_name, msg_type, msg):
    if msg is None:
        out_packet = "\n".join(['port:', str(sender_listening_port), "name", sender_name, "type:", msg_type])
    else:
        out_packet = "\n".join(['port:', str(sender_listening_port), "name", sender_name, "type:", msg_type, "msg:", msg])
    # print("packetFormat function finished, the result is ")
    # print(out_packet)
    return out_packet

def packetResolve(in_packet):
    # in_packet: has't been decoded
    in_packet = in_packet.decode()
    lines = in_packet.splitlines()
    sender_listening_port = int(lines[1])
    sender_name = lines[3]
    msg_type = lines[5]
    msg = lines[7] if len(lines) == 8 else None
    return sender_listening_port, sender_name, msg_type, msg


class Server:
    def __init__(self, server_listen_port):
        self.host = '127.0.0.1'
        self.server_listen_port = server_listen_port # client know this by default
        self.server_listen_socket = socket(AF_INET, SOCK_DGRAM)
        self.server_listen_socket.bind((self.host, self.server_listen_port))

        self.server_send_socket = socket(AF_INET, SOCK_DGRAM) # randomly assign a port number

        print(">>> Server is online")

        # disallow duplicate names entirely, even if the previous name-user already offline
        # nickname is like an id, uniquely identify each instance, no matter online or offline
        # allow registration of same (IP, port) if the previous user already offline
        # disallow change from offline to online, can only create a new account (otherwise hard to handle complex duplicate (ip, port) problem
        self.client_table = {}
        """
        client_table is a dictionary 
        {
            "clientName1": {
                "ip": '127.0.0.1', 
                "port": portNum1, (listening port)
                "online": True, 
            }, 
            "clientName2": {
                "ip": '127.0.0.1', 
                "port": portNum2, (listening port)
                "online": True,  
            }, ...
        } 
        """

        self.onlineMembers = set()

        # group name uniquely identify a group, disallow duplicated name
        # disallow ";" in groupname, because need to send group name list to client using ;
        self.group_table = {}
        """
        {
            "groupA_name": {"member1", "member2", ...},
            "groupB_name": {"member3", "member4", ...}, 
            ... 
        }
        """

        # acknowledgements of group messages received
        # Q: good format?
        # if senderA sends sequential grp msg (because already received ack from server, can move on to send another grp msg)
        # if senderA send grp msg, server deal with it, between then senderB send grp msg
        self.ack_dict = {}
        """
        {
            ("senderA", msg1_timestamp): {"member1": False, "member2": False, ...},
            ("senderB", msg1_timestamp): {"member3": False, "member4": False, ...}, 
            ...
        }
        """

        self.ack_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.group_lock = threading.Lock()

    def checkDuplicatedAddr(self, client_table, ip, port):
        """
        check if any onlineMember is using the (ip, port) combs, if so, new client cannot register with that addr
        notice that new client can use the same addr if the previous user is offline
        return: True (being taken); False (valid)
        """
        effective_addr = []
        for name, info in self.client_table.items():
            if info["online"]:
                effective_addr.append((info["ip"], info["port"]))
        if (ip, port) in effective_addr:
            return True
        return False

    def checkDuplicatedName(self, client_table, name):
        """
        check if the name is already in the table
        return: True (duplicated); False (valid)
        """

        if name in client_table:
            return True
        return False

    # main thread: sit listening for client req, but not ack
    def serverMode(self):
        while True:
            # print(">>> Server is listening")
            in_packet, addr = self.server_listen_socket.recvfrom(4096)
            sender_listening_port, sender_name, msg_type, in_msg = packetResolve(in_packet)
            sender_ip = addr[0]
            # sender_sending_port = addr[1] # useless

            # based on client's request, direct to corresponding server action
            if msg_type == "reg":
                """
                1) if client submit duplicated name/(ip,port), send ack with "not successful" msg
                2) else, send ack, with no additional msg, add client into table
                """

                regSuccess = False
                if self.checkDuplicatedName(self.client_table, sender_name):
                    out_msg = "Name taken."
                elif self.checkDuplicatedAddr(self.client_table, sender_ip, sender_listening_port):
                    out_msg = "(IP, port) combination taken."
                else:
                    out_msg = "Successfully registered."
                    # add client into client_table
                    self.client_table[sender_name] = {
                        "ip": sender_ip,
                        "port": sender_listening_port,
                        "online": True
                    }
                    # add client into onlineMembers list
                    self.onlineMembers.add(sender_name)
                    print(">>> Client table updated.")
                    print(self.client_table)
                    regSuccess = True
                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="reg_ack", msg=out_msg)

                # send ack to requested client (start the serverRespond thread)
                # NOTICE: each sender has two ports, should send to sender's listening port
                # Q: reason for using a sub-thread for respond: we want to quickly move on to the next round or while-loop,
                # so that server can listen to future incoming msg while processing the following req of the previous msg
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()
                # print("Server registration ack thread starts")

                if regSuccess:
                    # broadcast new client_table to all onlineMembers, do not need ack
                    # print("START: Broadcast client_table update to online members")
                    for onlineMember in self.onlineMembers:
                        out_msg = json.dumps(self.client_table)  # dict -> string
                        out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="table", msg=out_msg)
                        threading.Thread(target=self.serverRespond, args=(out_packet, self.client_table[onlineMember]["ip"], self.client_table[onlineMember]["port"])).start()
                    # print("FINISH: Broadcast client_table update to online members")

            elif msg_type == "dereg":
                # change the client's online status to "offline"
                self.client_table[sender_name]["online"] = False
                self.onlineMembers.remove(sender_name)
                print(">>> Client table updated.")
                print(self.client_table)

                # send ack to requested client (start the serverRespond thread)
                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=None)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

                # broadcast new client_table to all onlineMembers, do not need ack
                for onlineMember in self.onlineMembers:
                    out_msg = json.dumps(self.client_table)
                    out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="table", msg=out_msg)
                    threading.Thread(target=self.serverRespond, args=(out_packet, self.client_table[onlineMember]["ip"], self.client_table[onlineMember]["port"])).start()


            elif msg_type == "kick":
                # if clientA not received clientB's ack, clientA report to server, server change clientB to offline
                kick_name = in_msg

                # scenario: X dereg itself, then Y find out X is offline, so report to server,
                # but X already not in onlineMembers set, and X's online_status already changed to offline,
                # so client_table shouldn't be considered as updated
                if kick_name in self.onlineMembers:
                    self.client_table[kick_name]["online"] = False
                    self.onlineMembers.remove(kick_name)
                    print(">>> Client table updated.")
                    print(self.client_table)

                    # broadcast client_table
                    for onlineMember in self.onlineMembers:
                        out_msg = json.dumps(self.client_table)
                        out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="table", msg=out_msg)
                        threading.Thread(target=self.serverRespond, args=(out_packet, self.client_table[onlineMember]["ip"], self.client_table[onlineMember]["port"])).start()

                # need to send ack back, see explanation on client side
                # send ack to requested client (start the serverRespond thread)
                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=None)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()


            elif msg_type == "create_group":
                # check if the group name exists,
                group_name = in_msg
                with self.group_lock:
                    if group_name in self.group_table:
                        # NOTE: to check if a key is presented, better not use .get(), because will return False if value is NULL (e.g. an empty dict {})
                        out_msg = "exists"
                        print(f">>> Client {sender_name} creating group {group_name} failed, group already exists")
                    else:
                        self.group_table[group_name] = set()
                        print(f">>> Client {sender_name} created group {group_name} successfully")
                        out_msg = "created"
                        print(">>> Group table updated.")
                        print(self.group_table)

                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=out_msg)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

            elif msg_type == "list_groups":
                print(f">>> Client {sender_name} requested listing groups, current groups:")
                for group_name in self.group_table:
                    print(">>> " + group_name)

                # send ack with group_table  (start the serverRespond thread)
                with self.group_lock:
                    out_msg = ';'.join(list(self.group_table.keys())) # if group_table is empty, out_msg=None
                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=out_msg)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

            elif msg_type == "join_group":
                # check if the group name exists,
                group_name = in_msg
                with self.group_lock:
                    if group_name in self.group_table:
                        out_msg = "joined"
                        self.group_table[group_name].add(sender_name)
                        print(f">>> Client {sender_name} joined group {group_name}")
                        print(">>> Group table updated.")
                        print(self.group_table)
                    else:
                        print(f">>> Client {sender_name} joining group {group_name} failed, group does not exist")
                        out_msg = "not exists"

                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=out_msg)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

            elif msg_type == "list_members":
                group_name = in_msg
                with self.group_lock:
                    member_names = list(self.group_table[group_name])
                # check if sender still in group (because may be kick off before due to no-ack of grp-msg)
                if sender_name not in member_names:
                    out_msg = "already not in group"
                else:
                    out_msg = ";".join(member_names)  # members in that group, names seperated by ;
                    print(f">>> Client {sender_name} requested listing members of group {group_name}:")
                    for member_name in member_names:
                        print(">>> " + member_name)

                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=out_msg)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

            elif msg_type == "leave_group":
                # ADD: check if sender still in group (because may be kick off before due to no-ack of grp-msg)
                group_name = in_msg
                with self.group_lock:
                    member_names = list(self.group_table[group_name])

                    # check if sender still in group (because may be kick off before due to no-ack of grp-msg)
                    if sender_name not in member_names:
                        out_msg = "already not in group"
                    else:
                        out_msg = None
                        self.group_table[group_name].remove(sender_name)
                        print(f">>> Client {sender_name} left group")
                        print(">>> Group table updated.")
                        print(self.group_table)

                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=out_msg)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

            # server received acks from all other group members
            elif msg_type == "ack":
                grp_msg_receiver = sender_name
                # the below two elements uniquely identify a grp msg
                grp_msg_sender = in_msg.split(";")[0]
                msg_time = in_msg.split(";")[1]
                # print("Receved grp msg ack from" + grp_msg_receiver)
                # print("grp_msg_sender is: " + grp_msg_sender)
                # print("msg_time is: " + msg_time)

                # update ack_dict, need to lock ack dict
                with self.ack_lock:
                    # print("Modify ack_dict")
                    self.ack_dict[(grp_msg_sender, msg_time)][grp_msg_receiver] = True
                    # print("ack_dict looks like")
                    # print(self.ack_dict)


            elif msg_type == "send_group":
                """
                group_name;long_group_messages...
                """
                group_name = in_msg.split(";", maxsplit=1)[0]
                group_msg = in_msg.split(";", maxsplit=1)[1]
                print(f">>> Client {sender_name} sent group message: {group_msg}")

                with self.group_lock:
                    member_names = list(self.group_table[group_name])
                    # list of recipients, except sender.
                    # My def of recipients: all members in the group table, regardless of their online status
                    # Reason: since I disallow duplicated names, won't hurt if server tries to send to an offline client
                    # besides, this def allows server delete the offline client from group table, if no ack received
                    recipients = [member for member in self.group_table[group_name] if member != sender_name]

                # check if sender still in group (because may be kick off before due to no-ack of grp-msg)
                if sender_name not in member_names:
                    out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg="already not in group")
                    threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()
                    continue

                # if sender still in group, reply ack to sender
                out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="ack", msg=None)
                threading.Thread(target=self.serverRespond, args=(out_packet, sender_ip, sender_listening_port)).start()

                # add ack requirements into ack_dict, uniquely identify a grp_msg by (sender, curr_time)
                curr_time = str(time.time())
                with self.ack_lock:
                    # print("Modify ack_dict because someone send group msg")
                    self.ack_dict[(sender_name, curr_time)] = {recipient: False for recipient in recipients}
                    # print("ack_dict now looks like:")
                    # print(self.ack_dict)

                # broadcast group message to all group members except sender
                # do not need the spawn multiple parallel threads for this [small] implementation
                out_msg = ";".join([sender_name, curr_time, group_msg])
                """
                sender_name;curr_time;long_group_messages...
                """
                with self.send_lock:
                    for recipient in recipients:
                        out_packet = packetFormat(sender_listening_port=self.server_listen_port, sender_name="server", msg_type="grp_msg", msg=out_msg)
                        self.server_send_socket.sendto(out_packet.encode(), (self.client_table[recipient]["ip"], self.client_table[recipient]["port"]))

                # a sub-thread, first wait for 0.5 sec, then check if all acks are received, remove the nonresponsive clients from group
                # expect ack only from online clients (Q: def of online??)
                threading.Thread(target=self.sleep_and_wait_for_acks, args=(group_name, sender_name, curr_time)).start()

                # the main thread continue sitting and listening to incoming msg
                # possible incoming msg including ack from group-member recipients



    # sub thread: reply ack (with additional info) to client
    # each time job finished, this sub thread will automatically close
    def serverRespond(self, out_packet, target_ip, target_port):
        # reason for lock: send_socket send reg_ack, broadcast table to multiple clients in seperate sub-threads
        # print("Server respond thread start")
        # print("the out_packet is:")
        # print(out_packet)
        with self.send_lock:
            self.server_send_socket.sendto(out_packet.encode(), (target_ip, target_port))
            # print("Server respond thread finish")


    def sleep_and_wait_for_acks(self, group_name, sender_name, curr_time):
        # sleep for 0.5 sec
        time.sleep(0.5)

        # wake up, check if all acks are received
        # need to lock ack dict
        with self.ack_lock:
            # print("check nonresponsive recipients")
            nonresponsive_receivers = [receiver
                                       for receiver, ackReceived
                                       in self.ack_dict[(sender_name, curr_time)].items()
                                       if not ackReceived]
            # print("Nonresponsive:" + str(nonresponsive_receivers))

        # delete nonresponsive clients
        if nonresponsive_receivers:
            with self.group_lock:
                self.group_table[group_name] = self.group_table[group_name] - set(nonresponsive_receivers)
            for nonresponsive_receiver in nonresponsive_receivers:
                print(f">>> Client {nonresponsive_receiver} not responsive, removed from {group_name}")
            print(">>> Group table updated.")
            print(self.group_table)

        # delete the requirement pair, save space
        with self.ack_lock:
            del self.ack_dict[(sender_name, curr_time)]


class Client():
    def __init__(self, name, server_ip, server_listen_port, client_listen_port):
        self.name = name
        self.host = server_ip # assume client and server are always on the same machine

        self.client_listen_port = client_listen_port
        self.client_listen_socket = socket(AF_INET, SOCK_DGRAM)
        self.client_listen_socket.bind((self.host, self.client_listen_port))

        self.client_send_socket = socket(AF_INET, SOCK_DGRAM) # randomly assign a port number

        self.server_ip = server_ip
        self.server_listen_port = server_listen_port

        self.client_table = {}
        self.groupMode = False
        self.groupName = None
        self.pri_msg_queue = queue.Queue()
        """
        [(client1Name, msg1), (client2Name, msg2), ...]
        """

        # who send ack to this client, within the 0.5 sec time limit
        # only use port number to identify client
        # under assumption: everything on the same machine
        self.ack_dict = {} # need to update for each time of broadcast client_table
        """
        {
            "server": {
                "ack": False, 
                "info": "additional info"
            },
            "client1Name": {
                "ack": False, 
                "info": "additional info"
            },
            "client2Name": {
                "ack": False, 
                "info": "additional info"
            },
            ...
        }
        """

        self.ack_lock = threading.Lock()
        self.send_lock = threading.Lock()


    # main thread: take in user command
    def clientMode(self):

        # sub thread: sit aside, listening to all kinds of message (reg ack, broadcast table, group msg, private msg, all ack)
        self.thread_recv = threading.Thread(target=self.clientListen)
        self.thread_recv.start()
        print(">>> Client start listening", end="")

        # send registration request to the server
        out_packet = packetFormat(sender_listening_port=self.client_listen_port, sender_name=self.name, msg_type="reg", msg=None)
        self.client_send_socket.sendto(out_packet.encode(), (self.server_ip, self.server_listen_port))
        print("\n>>> Registration request sent", end="")


        # time.sleep(2)
        # take user input, send to target dest, sleep for 0.5 sec, after wake up, check global ack dict is ack is received
        # when waiting for ack for this input, cannot put in the next input
        while True:
            print("\n>>> ", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) ", end="")

            try:
                temp = input()
            except KeyboardInterrupt:
                # user close program by ctrl+C (recognized as KeyboardInterrupt in Python)
                os._exit(1)

            input_list = temp.split()
            # NEED TO ADD A LOT OF try...excep TO AVOID INDEX OUT OF BOUND ERROR
            try:
                command = input_list[0]
            except:
                print("\n>>> Invalid command", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) Invalid command", end="")
                continue

            # based on input command, determine target address
            if command == "send":
                # send private message
                target_name = input_list[1]
                try:
                    target_ip = self.client_table[target_name]["ip"]
                    target_port = self.client_table[target_name]["port"]
                except:
                    print(f"\n>>> User {target_name} does not exist", end="")
                    continue
            else:
                # send request to server
                target_name = "server"
                target_ip = self.server_ip
                target_port = self.server_listen_port

            # check (1) if the command is allowed, (2) if compatible to groupMode (3) other special requirement
            # construct send-out message
            if command == "send":
                """
                send private message to another client
                send <name> <long messages...>
                """
                if self.groupMode:
                    print(f"\n>>> ({self.groupName}) Invalid command", end="")
                    continue
                out_msg = "" # handle message with spaces
                for i in range(2, len(input_list)):
                    out_msg = out_msg + input_list[i] + " "
                msg_type = "pri_msg"

            elif command == "dereg":
                try:
                    dereg_name = input_list[1]
                except:
                    print("\n>>> Invalid command", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) Invalid command", end="")
                    continue
                # cannot dereg anyone else
                if dereg_name != self.name:
                    print("\n>>> Invalid command", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) Invalid command", end="")
                    continue
                out_msg = None
                msg_type = "dereg"

            elif command == "create_group":
                if self.groupMode:
                    print(f"\n>>> ({self.groupName}) Invalid command", end="")
                    continue
                # make sure a group name is followed
                try:
                    group_name = input_list[1]
                except:
                    print("\n>>> Invalid command", end="")
                    continue
                if ";" in group_name:
                    print("\n>>> Group name should not contain ';'. Try again.", end="")
                    continue
                out_msg = group_name
                msg_type = "create_group"

            elif command == "list_groups":
                if self.groupMode:
                    print(f"\n>>> ({self.groupName}) Invalid command", end="")
                    continue
                out_msg = None
                msg_type = "list_groups"

            elif command == "join_group":
                if self.groupMode:
                    print(f"\n>>> ({self.groupName}) Invalid command", end="")
                    continue
                # make sure a group name is followed
                try:
                    group_name = input_list[1]
                except:
                    print("\n>>> Invalid command", end="")
                    continue
                out_msg = group_name
                msg_type = "join_group"

            elif command == "send_group":
                """
                send_group <long messages...>
                """
                if not self.groupMode:
                    print("\n>>> Invalid command", end="")
                    continue
                # include group name at the start of msg, for the server to determine group members
                out_msg = self.groupName + ";"
                # handle message with spaces
                for i in range(1, len(input_list)):
                    out_msg = out_msg + input_list[i] + " "
                msg_type = "send_group"

            elif command == "list_members":
                if not self.groupMode:
                    print("\n>>> Invalid command", end="")
                    continue
                out_msg = self.groupName
                msg_type = "list_members"

            elif command == "leave_group":
                if not self.groupMode:
                    print("\n>>> Invalid command", end="")
                    continue
                out_msg = self.groupName
                msg_type = "leave_group"

            else:
                # other user inputs that cannot be recognized
                print("\n>>> Invalid command", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) Invalid command", end="")
                continue


            # send request/message to server/other_client, retry for 5 times
            num_retries = 0
            while num_retries < 5:
                out_packet = packetFormat(sender_listening_port=self.client_listen_port, sender_name=self.name, msg_type=msg_type, msg=out_msg)
                with self.send_lock:
                    self.client_send_socket.sendto(out_packet.encode(), (target_ip, target_port))

                # create the ack requirement
                with self.ack_lock:
                    self.ack_dict[target_name] = {"ack": False, "info": None}

                # sleep for 0.5 sec
                time.sleep(0.5)

                # wake up, check the ack dict whether ack is received
                # client only has to deal with single ack at a time
                with self.ack_lock:
                    ackReceived = self.ack_dict[target_name]["ack"]
                    additional_info = self.ack_dict[target_name]["info"]
                if ackReceived:
                    # change the flag back to False, for future ack to use
                    self.ack_dict[target_name] = {"ack": False, "info": None}

                    # based on command, print corresponding msg
                    if command == "send":
                        print(f"\n>>> Message received by {target_name}.", end="")

                    elif command == "dereg":
                        print("\n>>> You are Offline. Bye.", end="")
                        while not self.pri_msg_queue.empty():
                            pri_sender, cached_msg = self.pri_msg_queue.get()
                            print("\n>>> " + pri_sender + ": " + cached_msg, end="")

                        os._exit(1)

                    elif command == "create_group":
                        if additional_info == "created":
                            print(f"\n>>> Group {group_name} created by Server.", end="")
                        elif additional_info == "exists":
                            print(f"\n>>> Group {group_name} already exists.", end="")

                    elif command == "list_groups":
                        if additional_info:
                            # if addition_info is not None
                            grp_names = additional_info.split(";")
                            print("\n>>> Available group chats:", end="")
                            for grp_name in grp_names:
                                print("\n>>> " + grp_name, end="")
                        else:
                            print("\n>>> No available group right now", end="")

                    elif command == "join_group":
                        if additional_info == "joined":
                            self.groupMode = True
                            self.groupName = group_name
                            print(f"\n>>> Entered group {group_name} successfully", end="")
                        elif additional_info == "not exists":
                            print(f"\n>>> Group {group_name} does not exist", end="")

                    elif command == "send_group":
                        if additional_info == "already not in group":
                            print("\n>>> You're already not in the group, because the Server didn't receive your previous ack to a group message.", end="")
                            self.groupMode = False
                            self.groupName = None
                            # check if pri_msg_queue is empty, if not, print out all msg
                            while not self.pri_msg_queue.empty():
                                pri_sender, cached_msg = self.pri_msg_queue.get()
                                print("\n>>> " + pri_sender + ": " + cached_msg, end="")
                        else:
                            print(f"\n>>> ({self.groupName}) Message received by Server.", end="")

                    elif command == "list_members":
                        if additional_info == "already not in group":
                            print("\n>>> You're already not in the group, because the Server didn't receive your previous ack to a group message.", end="")
                            self.groupMode = False
                            self.groupName = None
                            # check if pri_msg_queue is empty, if not, print out all msg
                            while not self.pri_msg_queue.empty():
                                pri_sender, cached_msg = self.pri_msg_queue.get()
                                print("\n>>> " + pri_sender + ": " + cached_msg, end="")
                        else:
                            print(f"\n>>> ({self.groupName}) Members in the group {self.groupName}:", end="")
                            member_names = additional_info.split(";")
                            for member_name in member_names:
                                print(f"\n>>> ({self.groupName}) " + member_name, end="")

                    elif command == "leave_group":
                        if additional_info == "already not in group":
                            print("\n>>> You're already not in the group, because the Server didn't receive your previous ack to a group message.", end="")
                            self.groupMode = False
                            self.groupName = None
                        else:
                            print(f"\n>>> Leave group chat {self.groupName}", end="")
                            self.groupMode = False
                            self.groupName = None

                        # check if pri_msg_queue is empty, if not, print out all msg
                        while not self.pri_msg_queue.empty():
                            pri_sender, cached_msg = self.pri_msg_queue.get()
                            print("\n>>> " + pri_sender + ": " + cached_msg, end="")

                    break

                num_retries += 1

            if num_retries == 5: # this judgement seems unnecessary
                if command == "send":
                    # receiver-side client no respond, already offline
                    print(f"\n>>> No ACK from {target_name}, message not delivered", end="")

                    print("\n>>> Report this issue to server", end="")
                    # report to server, server have to update and broadcast client table, do not need ack
                    out_packet = packetFormat(sender_listening_port=self.client_listen_port, sender_name=self.name, msg_type="kick", msg=target_name)
                    with self.send_lock:
                        self.client_send_socket.sendto(out_packet.encode(), (self.server_ip, self.server_listen_port))

                    # should expect an ack of kick from server, because if server already offline, the client should know and exit;
                    # if server still online, we can therefore ensure client's client_table is updated
                    # otherwise, when server and clientY are both offline,  client X's table will never be updated and keep trying to send msg to Y

                    # create the ack requirement
                    with self.ack_lock:
                        self.ack_dict["server"] = {"ack": False, "info": None}

                    # sleep for 0.5 sec
                    time.sleep(0.5)

                    # wake up, check the ack dict whether ack is received
                    # client only has to deal with single ack at a time
                    with self.ack_lock:
                        ackReceived = self.ack_dict["server"]["ack"]
                    if not ackReceived:
                        # server not respond
                        prefix = "(" + self.groupName + ") " if self.groupMode else ""
                        print("\n>>> " + prefix + "Server not responding", end="")
                        print("\n>>> " + prefix + "Exiting", end="")
                        os._exit(1)
                    else:
                        # change the flag back to False, for future ack
                        self.ack_dict["server"] = {"ack": False, "info": None}

                else:
                    # server not respond
                    prefix = "("+ self.groupName + ") " if self.groupMode else ""
                    print("\n>>> " + prefix + "Server not responding", end="")
                    print("\n>>> " + prefix + "Exiting", end="")

                    # print out the remaining private msg in cache
                    # scenario: X normal, Y group; server goes down; X send to Y, Y cache; Y req to server, find out server down; Y print X's msg before exiting
                    # check if pri_msg_queue is empty, if not, print out all msg
                    while not self.pri_msg_queue.empty():
                        pri_sender, cached_msg = self.pri_msg_queue.get()
                        print("\n>>> " + pri_sender + ": " + cached_msg, end="")

                    os._exit(1)

                    # ADD: client kill itself (Q: how?)



    # keep listening on messages (broadcast table, group msg, private msg, [ack])
    # if received ack, modify global ack dictionary
    def clientListen(self):
        while True:
            data, addr = self.client_listen_socket.recvfrom(4096)
            sender_listening_port, sender_name, msg_type, in_msg = packetResolve(data)
            sender_ip = addr[0]
            sender_sending_port = addr[1]

            if msg_type == "reg_ack":
                if in_msg == "Successfully registered.":
                    print("\n>>> Welcome, You are registered.", end="")
                elif in_msg == "Name taken.":
                    print("\n>>> Someone has already used this name. Try another one.", end="")
                    os._exit(1) # kill the whole program (main and sub thread), in this listen sub-thread
                elif in_msg == "(IP, port) combination taken.":
                    print("\n>>> Someone has already used this (IP, port) combination. Try another one.", end="")
                    os._exit(1)

            elif msg_type == "table":
                # received from server, update local client table
                self.client_table = json.loads(in_msg) # string to dict
                prefix = "(" + self.groupName + ") " if self.groupMode else ""
                print("\n>>> "+ prefix + "Client table updated.", end="")
                print("\n" + str(self.client_table), end="")
                print("\n>>> ", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) ", end="")
                # because you don't know the next print would be input command or sth triggered by incoming msg
                # maybe the ">>>" from input command already printed out before

            elif msg_type == "grp_msg":
                # received from server
                # print("receive grp msg from server")
                # print("in_msg is:")
                # print(in_msg)
                grp_msg_sender = in_msg.split(";", maxsplit=2)[0]
                msg_time = in_msg.split(";", maxsplit=2)[1]
                msg_content = in_msg.split(";", maxsplit=2)[2]

                # reply ack to server, regarding this specific group memessage (sender, time)
                out_packet = packetFormat(sender_listening_port=self.client_listen_port, sender_name=self.name,
                                          msg_type="ack", msg=grp_msg_sender + ";" + msg_time)
                with self.send_lock:
                    self.client_send_socket.sendto(out_packet.encode(), (sender_ip, sender_listening_port))

                # print out group message
                print("\n>>> (" + self.groupName + ") Group_Message " + grp_msg_sender + ": " + msg_content, end="")
                print("\n>>> ", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) ", end="")

            elif msg_type == "pri_msg":
                # send ack to sender client
                # need to lock client_send_socket
                out_packet = packetFormat(sender_listening_port=self.client_listen_port, sender_name=self.name,
                                          msg_type="ack", msg=None)
                with self.send_lock:
                    self.client_send_socket.sendto(out_packet.encode(), (sender_ip, sender_listening_port))

                if self.groupMode:
                    # place private message in private message queue
                    self.pri_msg_queue.put((sender_name, in_msg))
                else:
                    # print out private message
                    print(f"\n>>> {sender_name}: " + in_msg, end="")
                    print("\n>>> ", end="") if not self.groupMode else print(f"\n>>> ({self.groupName}) ", end="")

            elif msg_type == "ack":
                # differentiate where this ack comes from, by sender_name
                # update global ack table of that ack-sender
                # need to lock act dict
                with self.ack_lock:
                    # write into ack_dict
                    self.ack_dict[sender_name]["ack"] = True
                    self.ack_dict[sender_name]["info"] = in_msg



if __name__ == "__main__":
    # check if the command line input is valid
    if len(sys.argv) < 2:
        print("Please use valid input like:")
        print("python ChatApp.py -s <port> OR python ChatApp.py -c <name> <server-ip> <server-port> <client-port>")
        sys.exit(1)
        # the script will terminate with a status code 1 indicating an error
        # NOTE: sys.exit() only terminate the thread where it's called

    mode = sys.argv[1]

    if mode == '-s':
        if len(sys.argv) != 3:
            print("Please use valid input like:")
            print("python ChatApp.py -s <port>")
            sys.exit(1)

        try:
            server_listen_port = int(sys.argv[2])
        except:
            print("Invalid server port number")
            sys.exit(1)
        if not (server_listen_port >= 1024 and server_listen_port <= 65535):
            print("Invalid server port number")
            sys.exit(1)

        server = Server(server_listen_port)
        server.serverMode()


    elif mode == '-c':
        if len(sys.argv) != 6:
            print("Please use valid input like:")
            print("python ChatApp.py -c <name> <server-ip> <server-port> <client-port>")
            sys.exit(1)

        # check name is valid, because I use name as a unique id, should not use the server's name
        # besides, name should not contain ";", because I use this to seperate group member names
        name = sys.argv[2]
        if name == "server" or ";" in name:
            # in fact, ';' can never be in name because CLI doesn't allow this character...
            print("Invalid username")
            sys.exit(1)

        server_ip = sys.argv[3]
        match = re.match(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", server_ip)
        if not (server_ip == "localhost" or bool(match)):
            print("Invalid server ip address. Try again.")
            sys.exit(1)

        try:
            server_listen_port = int(sys.argv[4])
        except:
            print("Invalid server port number. Try again.")
            sys.exit(1)

        if not (server_listen_port >= 1024 and server_listen_port <= 65535):
            print("Invalid server port number")
            sys.exit(1)

        try:
            client_listen_port = int(sys.argv[5])
        except:
            print("Invalid client port number")
            sys.exit(1)
        if not (client_listen_port >= 1024 and client_listen_port <= 65535):
            print("Invalid client port number")
            sys.exit(1)

        client = Client(name, server_ip, server_listen_port, client_listen_port)
        client.clientMode()

    else:
        print("Please use valid input like:")
        print("python ChatApp.py -s <port> OR python ChatApp.py -c <name> <server-ip> <server-port> <client-port>")
        sys.exit(1)
