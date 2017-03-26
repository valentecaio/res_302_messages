import queue
import socket
import threading
from time import sleep

import messages as m

try:
	from pprint import pprint
except:
	pprint = print

clients = {}
next_client_id = 1
next_group_id = 1
UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = ('localhost', 1212)
messages_queue = queue.Queue()

# constants
ST_CONNECTING = 0
ST_CONNECTED = 1

PUBLIC_GROUP = 1

#checks if username is already in the list. returns True if username is ok and fals if there is already somebody using it
def check_username(username):
	for id, client in clients.items():
		if client['username'] == username:
			return False
	return True


# add client to clients list
def connect_client(addr, username):
	# add client to clients dict
	global next_client_id
	client_id = next_client_id
	next_client_id += 1

	client = {'id': client_id, 'addr': addr, 'username': username, 'state': ST_CONNECTING, 'group': PUBLIC_GROUP}
	clients[client_id] = client

	print('Connected to a new client: \t', client)
	return client


# receive a coded message and send it to receivers list
def send_message(msg, receivers):
	for id, client in receivers.items():
		UDPSock.sendto(msg, client['addr'])
		print("Sent msg to client " + str(id))


# function to update the list of all users if somebody joined or changed status.
# Input is a dictionary of the users that changed
def update_user_list(updated_users):
	for id, client in clients.items():
		msg = m.createUpdateList(0, updated_users)
		UDPSock.sendto(msg, client['addr'])
	return


''' thread functions '''


def receive_data():
	while 1:
		# receive message
		data, addr = UDPSock.recvfrom(1024)
		if not data: break

		# put new message in the queue
		messages_queue.put_nowait({'data': data, 'addr': addr})


def send_data():
	while 1:
		global next_group_id

		# try to get a message from the queue
		# if there's no message, try again without blocking
		try:
			input = messages_queue.get(block=False)
			data, addr = input['data'], input['addr']
		except:
			continue

		# unpack header
		header = m.unpack_header(data)
		msg_type = header['type']
		source_id = header['sourceID']

		# treat acknowledgement messages according to types
		if header['A']:
			print('Received acknowledgement of type ' + str(msg_type))
			if msg_type == m.TYPE_CONNECTION_ACCEPT:
				# code enter here when receiving a connectionAccept acknowledgement
				# change client state to connected
				client = clients[source_id]
				client['state'] = ST_CONNECTED
				# update list of other users
				updated_user = {source_id: client}
				update_user_list(updated_user)
			elif msg_type == m.TYPE_USER_LIST_RESPONSE:
				# code enter here when receiving a userListResponse acknowledgement
				pass
			# elif ...

		# treat non-acknowledgement messages
		else:
			if msg_type == m.TYPE_CONNECTION_REQUEST:
				# get username from message content
				username = header['content'].decode().strip()
				#checks username and responses according to that check (allows or denies connection)
				if check_username(username) == True:
					if len(clients) < 250:
						# add client to clients list
						client = connect_client(addr, username)
						# send ConnectionAccept as response
						response = m.createConnectionAccept(0, client['id'])
						UDPSock.sendto(response, client['addr'])
						print('sent connectionAccept to client')
					else:
						#send error code 0 for maximum of members on the server
						response = m.createConnectionReject(0,0)
						UDPSock.sendto(response, addr)
				else:
					#send error code 1 for username already taken
					response = m.createConnectionReject(0,1)
					UDPSock.sendto(response, addr)

			elif msg_type == m.TYPE_DATA_MESSAGE:
				# get message text
				# should send ack
				content = header['content']
				text = content[2:]
				print("%s >> %s" % (header['sourceID'], text.decode()))
				groupID = header['groupID']

				# resend it to users in same group
				receivers = {}

				for id,client in clients.items():
					if client['group'] == groupID:
						receivers[id] = clients[id]
				send_message(data, receivers)

			elif msg_type == m.TYPE_USER_LIST_REQUEST:
				# send user list
				response = m.createUserListResponse(0, source_id, clients)
				print('send user list to client ' + str(source_id))
				UDPSock.sendto(response, clients[source_id]['addr'])

			elif msg_type == m.TYPE_DISCONNECTION_REQUEST:
				del clients[source_id]
				response = m.acknowledgement(msg_type, 0, source_id)
				UDPSock.sendto(response, clients[source_id]['addr'])
				# tell other clients that user disconnected
				update_disconnection = m.updateDissconnction(0, source_id)
				send_message(update_disconnection, clients)

			elif msg_type == m.TYPE_GROUP_CREATION_REQUEST:
				group_type, members = m.unpack_group_creation_request(data)
				print("User %s is inviting members %s to a group of type %s"
					  % (source_id, members, group_type))

				ack = m.acknowledgement(m.TYPE_GROUP_CREATION_REQUEST, 0, source_id)
				UDPSock.sendto(ack,clients[source_id]['addr'])

				group_id = next_group_id
				next_group_id += 1

				for id in members:
					invitation = m.groupInvitationRequest(0, source_id,
														  group_type, group_id,
														  id)
					UDPSock.sendto(invitation, clients[id]['addr'])
					print('Sent invitation to client ' + str(id))


def run_threads():
	# start a thread to receive data
	sender_thread = threading.Thread(target=receive_data)
	sender_thread.daemon = True
	sender_thread.start()

	# start a thread to hang sending messages
	sender_thread = threading.Thread(target=send_data)
	sender_thread.daemon = True
	sender_thread.start()

	# hang program execution
	while 1:
		sleep(10)


if __name__ == '__main__':
	UDPSock.bind(server_address)
	print("Server started at address", server_address)
	run_threads()
