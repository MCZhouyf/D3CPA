# generate data of different biomes at different times of the day
from re import T
import minedojo
import random
import string
import numpy as np
from PIL import Image
import math
import pickle
from minedojo.sim import InventoryItem
import numpy as np
from minedojo.sim.mc_meta import mc as MC
import pdb
from utils import *
# work done by lqc and what remains to be done (short-term goals):
# 1. I have modified mine_ahead but haven't checked its effect.
# 2. I have modified underground strategy (so that the agent's current underground strategy
#    is to go in straight line no matter what), but this strategy isn't flexible and needs improvement
# 3. I have modified move_to_middle: may still be problems.
# 4. I have solved some problems with approach, but approach strategy still needs improvement. (modify try_forward, try_leftward and try_rightward)
# 5. I have modified the mine function to better aim: aim has improved but there may still be problems.
# 6. Need to devise strategy to deal with water.
# 7. If you want to observe and interact with entities, need to scan entity_name array in addition to the block_name array.
# 8. Counting of inventory items may sometimes be faulty.

save_count = 0
dontstop = 0
steplen = 0.098 
seed = 0
vradius = 5# voxel observation radius should be consistent with lidar range
events = {}
prev_position = np.array([0,0,0])
explore_steps = 0 # keep as global variable
try_steps = 0
action_stack = []# each element is a tuple with 2 dimensions (dir,jumpornot)
stuck = 0
recently_approached_object_position = []# stores the position of the recently approached object

# Create_observation creates a txt file containing ground-truth observations provided by the minedojo interface
# under the directory SA_observation, note that you will have to create the SA_observation directory under the  
# work directory in advance.
def create_observation(env,ii):
    observation = ""
    events  = sleep(env)
    # Location Statistics
    if 'location_stats' in events:
        observation += f"Location Statistics:\n"
        observation += f"  - Position: {events['location_stats']['pos']}\n"
        observation += f"  - Compass (Yaw/Pitch): {events['location_stats']['yaw']}, {events['location_stats']['pitch']}\n"
        observation += f"  - Biome ID: {events['location_stats']['biome_id']}\n"
        observation += f"  - Rainfall: {events['location_stats']['rainfall']}\n"
        observation += f"  - Temperature: {events['location_stats']['temperature']}\n"
        observation += f"  - Can See Sky: {events['location_stats']['can_see_sky']}\n"
        observation += f"  - Is Raining: {events['location_stats']['is_raining']}\n"
        observation += f"  - Light Level: {events['location_stats']['light_level']}\n"
        observation += f"  - Sky Light Level: {events['location_stats']['sky_light_level']}\n"
        observation += f"  - Sun Brightness: {events['location_stats']['sun_brightness']}\n"
        observation += f"  - Sea Level: {events['location_stats']['sea_level']}\n\n"

  # Voxels
    if 'voxels' in events:
        observation += f"Voxels:\n"
        # observation += f"Looking Angle: {events['voxels']['cos_look_vec_angle']}"
        # observation += f"  - Block Names: {events['voxels']['block_name']}\n"
        # Create a 3D NumPy array of shape (21, 21, 21) for demonstration purposes


        # Iterate through the 3D array and append its elements to the string
        for i in range(events['voxels']['block_name'].shape[0]):
            for j in range(events['voxels']['block_name'].shape[1]):
                for k in range(events['voxels']['block_name'].shape[2]):
                    # Convert the element to a string and append it to 'observation'
                    observation += str(events['voxels']['block_name'][i, j, k]) + " "
                observation+='\n'
            observation +='\n'

        # You can remove the trailing space if needed
        # observation = observation.strip()

        # Print the resulting string
            
    
    if 'inventory' in events:
        observation += f"Inventory:\n"
        observation += f"  - Name: {events['inventory']['name']}\n"
        observation += f"  - Quantity: {events['inventory']['quantity']}\n"
        observation += f"  - Variant: {events['inventory']['variant']}\n"
        observation += f"  - Current Durability: {events['inventory']['cur_durability']}\n"
        observation += f"  - Max Durability: {events['inventory']['max_durability']}\n\n"


    # Nearby Tools
    if 'nearby_tools' in events:
        observation += f"Nearby Tools:\n"
        observation += f"  - Is Crafting Table Nearby: {events['nearby_tools']['table']}\n"
        observation += f"  - Is Furnace Nearby: {events['nearby_tools']['furnace']}\n\n"

    # Privileged Observation
    if 'rays' in events:
        observation += "LIDAR OBSERVATION\n"
        observation += "Lidar observations mainly include three parts: information about traced entities, properties of traced blocks, and directions of lidar rays themselves.\n"
        observation += f"  - Block Name: {events['rays']['block_name']}\n"
        observation += f"  - Block Distance: {events['rays']['block_distance']}\n"
        observation += f"  - Block Variant: {events['rays']['block_meta']}\n"
        observation += f"  - Block Position: ({events['rays']['traced_block_x']}, {events['rays']['traced_block_y']}, {events['rays']['traced_block_z']})\n"
        observation += f"  - Ray Yaw: {events['rays']['ray_yaw']}\n"
        observation += f"  - Ray Pitch: {events['rays']['ray_pitch']}\n"
        observation += f"  - Entity Name: {events['rays']['entity_name']}\n"
        observation += f"  - Entity Distance: {events['rays']['entity_distance']}\n"
    # with open (f"SA_observation/{ii}.txt",'w') as file:
    #     file.write(observation)
    # save_rgb_as_image(env,f"{ii}")
    return observation

# Saves a screenshot under SA_screenshots, the SA_screenshots directory must likewise be created in advance.
# Screenshot will be named by the string parameter you pass to the function.
def save_rgb_as_image(env,name):
    events  = sleep(env)
    rgb_frame = events["rgb"]
    file_path = f"../images/{name}.jpg"
    image = Image.fromarray(rgb_frame.transpose(1,2,0))
    image.save(file_path)

def save_rgb_for_video(events):
    global save_count
    save_count += 1
    rgb_frame = events["rgb"]
    file_path = f"../video/frame_{save_count}.jpg"
    image = Image.fromarray(rgb_frame.transpose(1,2,0))
    image.save(file_path)

# Generates a random string of numbers of length 8
def generate_random_string(env,):
    events  = sleep(env)
    return ''.join(str(random.randint(0,9)) for _ in range(8))

# Decides if target object is within lidar range.
# This function should be replaced.
def lidar_detect(env,object):
    events  = sleep(env)
    if np.isin(object,events['rays']['block_name']):
        return True
    else:
        return False
    
def surrounding_voxel_detect(env,object):
    events  = sleep(env)
    detect_success = False
    # print(events['voxels']['block_name'])
    # right down
    if (events['voxels']['block_name'][vradius][vradius][vradius+1]==object):
        detect_success = True
    # right top
    if (events['voxels']['block_name'][vradius][vradius+1][vradius+1]==object):
        detect_success = True
    # forward down
    if (events['voxels']['block_name'][vradius+1][vradius][vradius]==object):
        detect_success = True
    # forward top
    if (events['voxels']['block_name'][vradius+1][vradius+1][vradius]==object):
        detect_success = True
    # left down
    if (events['voxels']['block_name'][vradius][vradius][vradius-1]==object):
        detect_success = True
    # left top
    if (events['voxels']['block_name'][vradius][vradius+1][vradius-1]==object):
        detect_success = True
    # top 
    if (events['voxels']['block_name'][vradius][vradius+2][vradius]==object):
        detect_success = True
    # down
    if (events['voxels']['block_name'][vradius][vradius-1][vradius]==object):
        detect_success = True
    return detect_success

    
# This function is not used.
def voxel_detect(env,object):
    events  = sleep(env)
    if np.isin(object,events['voxels']['block_name']):
        return True
    else:
        return False
    
# # older version
# def move_to_middle(env):# move to middle of block(upon which you are standing)
#     # moving forward
#     events  = sleep(env)
#     numerator = float(math.floor(events['location_stats']['pos'][0])+0.5-float(events['location_stats']['pos'][0]))
#     stepnum = numerator / steplen 
#     delta = stepnum - math.floor(stepnum)
#     if (delta>0.5):
#         stepnum = math.ceil(stepnum)
#     else:
#         stepnum = math.floor(stepnum) 
#     if (stepnum > 0):
#         for i in range(stepnum):
#             events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     elif (stepnum < 0):
#         for i in range(-stepnum):
#             events,_,_,_ = env.step([2,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     # moving rightward
#     numerator = float(float(math.ceil(events['location_stats']['pos'][2])+0.5-float(events['location_stats']['pos'][2])))
#     stepnum = numerator / steplen 
#     delta = stepnum - math.floor(stepnum)
#     if (delta>0.5):
#         stepnum = math.ceil(stepnum)
#     else:
#         stepnum = math.floor(stepnum) 
#     if (stepnum > 0):
#         for i in range(stepnum):
#             events,_,_,_ = env.step([0,2,0,12,12,0,0,0]); save_rgb_for_video(events)
#     elif (stepnum < 0):
#         for i in range(-stepnum):
#             events,_,_,_ = env.step([0,1,0,12,12,0,0,0]); save_rgb_for_video(events)
#     print(f"present location is {events['location_stats']['pos']}")

def move_to_middle(env):# Move to middle of block(upon which you are standing).
    events  = sleep(env)
    start_x = events['location_stats']['pos'][0]
    start_z = events['location_stats']['pos'][2]
    target_x = math.floor(start_x) + 0.5
    target_z = math.floor(start_z) + 0.5

    delta = start_x - math.floor(start_x)
    print(f"perpendicular delta is {delta}")
    no_progress = 0
    for _ in range(10):
        current_x = events['location_stats']['pos'][0]
        if target_x - 0.05 <= current_x <= target_x + 0.05:
            break
        prev_x = current_x
        step = [1,0,0,12,12,0,0,0] if current_x < target_x else [2,0,0,12,12,0,0,0]
        events,_,_,_ = env.step(step); save_rgb_for_video(events)
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
        current_x = events['location_stats']['pos'][0]
        if step[0] == 1:
            print(f"moving forward, present position is {current_x}")
        else:
            print(f"moving back, present position is {current_x}")
        if abs(current_x - prev_x) < 1e-3:
            no_progress += 1
            if no_progress >= 2:
                break
        else:
            no_progress = 0

    delta = start_z - math.floor(start_z)
    print(f"horizontal delta is {delta}")
    no_progress = 0
    for _ in range(10):
        current_z = events['location_stats']['pos'][2]
        if target_z - 0.05 <= current_z <= target_z + 0.05:
            break
        prev_z = current_z
        step = [0,2,0,12,12,0,0,0] if current_z < target_z else [0,1,0,12,12,0,0,0]
        events,_,_,_ = env.step(step); save_rgb_for_video(events)
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
        current_z = events['location_stats']['pos'][2]
        if step[1] == 2:
            print(f"moving right, present position is {current_z}")
        else:
            print(f"moving left, present position is {current_z}")
        if abs(current_z - prev_z) < 1e-3:
            no_progress += 1
            if no_progress >= 2:
                break
        else:
            no_progress = 0

    print(f"moving to middle, present location is {events['location_stats']['pos']}")

    
# This function returns object's relative location if desired object is within close proximity.
# The nearby function and the approach function can only target inanimate objects(tbd).
def nearby(env,object):
    events  = sleep(env)
    for i in range(vradius-1,vradius+2):
        for j in range(vradius-1,vradius+3):
            for k in range(vradius-1,vradius+2):
                # Convert the element to a string and append it to 'observation'
                if (object == events['voxels']['block_name'][i][j][k]):
                    new_tuple = (i,j,k)
                    return new_tuple
    new_tuple = (-1,-1,-1)
    return new_tuple


def interaction_ready(target_block, object_name=None):
    if target_block is None:
        return False
    if object_name == "wood":
        return (
            target_block["forward_offset"] <= 1
            and abs(target_block["side_offset"]) <= 1
            and abs(target_block["vertical_offset"]) <= 1
        )
    return (
        target_block["forward_offset"] <= 1
        and abs(target_block["side_offset"]) == 0
        and abs(target_block["vertical_offset"]) <= 1
    )

# # This function is not used.
# def mine_around(target,equipment):
#     events  = sleep(env)
#     if np.isin(target,events['rays']['block_name']):
#         indices = np.where(events['rays']['block_name'] == target)[0]
#         positions = []
#         for idx in indices:
#             if events['rays']['block_distance'][idx] < 3:
#                 print(f"check if {events['rays']['block_name'][idx]} is {target}")
#                 positions.append(idx)
#         if (positions):
#             print(f"mining around with positions {positions}")
#             for pos in positions:
#                 quotient, remainder = divmod(pos+1, 25)
#                 xangle, remainder = divmod((13-remainder),3)
#                 yangle,remainder = divmod((13-quotient),3)
#                 events,_,_,_ = env.step([0,0,0,12,12+xangle,0,0,0]); save_rgb_for_video(events)
#                 events,_,_,_ = env.step([0,0,0,12+yangle,12,0,0,0]); save_rgb_for_video(events)
#                 for i in range(10):
#                     events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
#                     save_rgb_as_image(env,f"{i}")
#                 events,_,_,_ = env.step([0,0,0,12,13,0,0,0]); save_rgb_for_video(events)# turn slightly
#                 for i in range(10):
#                     events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
#                     save_rgb_as_image(env,f"again{i}")
#                 events,_,_,_ = env.step([0,0,0,12,11,0,0,0]); save_rgb_for_video(events)# recover from slight turn
#                 events,_,_,_ = env.step([0,0,0,12,12-xangle,0,0,0]); save_rgb_for_video(events)
#                 events,_,_,_ = env.step([0,0,0,12-yangle,12,0,0,0]); save_rgb_for_video(events)# return to initial angle
#     elif np.isin(object,events['rays']['entity_name']):
#         indices = np.where(events['rays']['entity_name'] == target)[0]
#         positions = []
#         for idx in indices:
#             if events['rays']['entity_distance'][idx] < 2:
#                 positions.append(indices[idx])
#         if (positions):
#             print(f"mining around")
#             for pos in positions:
#                 quotient, remainder = divmod(pos+1, 25)
#                 xangle, remainder = divmod((13-remainder),3)
#                 yangle,remainder = divmod((13-quotient),3)
#                 events,_,_,_ = env.step([0,0,0,12,12+xangle,0,0,0]); save_rgb_for_video(events)
#                 events,_,_,_ = env.step([0,0,0,12+yangle,12,0,0,0]); save_rgb_for_video(events)
#                 for i in range(10):
#                     events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
#                     save_rgb_as_image(env,f"{i}")
#                 events,_,_,_ = env.step([0,0,0,12,13,0,0,0]); save_rgb_for_video(events)# turn slightly
#                 for i in range(10):
#                     events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
#                     save_rgb_as_image(env,f"again{i}")
#                 events,_,_,_ = env.step([0,0,0,12,11,0,0,0]); save_rgb_for_video(events)# recover from slight turn
#                 events,_,_,_ = env.step([0,0,0,12,12-xangle,0,0,0]); save_rgb_for_video(events)
#                 events,_,_,_ = env.step([0,0,0,12-yangle,12,0,0,0]); save_rgb_for_video(events)# return to initial angle


# Action_mine is the structured action for mining a target number of desired objects using specified equipment.
# The function loops infinitely, executing explore -> approach -> mine until the number of objects satisfy the agent's need (>= goalum)
# if agent is above ground. If agent is underground, the function executes explore -> mine in the loop, omitting the approach phase as it is
# assumed that agent must be in mining distance of desired object if he can see it underground.
'''
def action_mine(env,object,equipment,underground,goal_num):
    events  = sleep(env)
    # for i in range(goal_num):
    #     print(f"the {i}th mine in {goal_num} times")
    #     explore_above_ground(object,underground,10)
    #     approach(object,underground)
    #     mine(object,equipment)
    
    inventory = events['inventory']['name'].tolist()
    indices = []
    totalnum = 0
    prevnum = -1# num of objects in inventory directly after last mine
    target_object = ""
    trynum = 0
    if object == "wood":
        target_object = "log"
    elif object == "stone":
        target_object = "cobblestone"
    elif object =="diamond":
        target_object = "diamond  ore"
    else:
        target_object = object
    try:
        indices = [index for index, value in enumerate(inventory) if value == target_object]
    except ValueError:
        indices = []
        print(f"no equipment {equipment} found--------")
    if (indices):
        events = sleep(env)
        totalnum = 0
        for index in indices:
            totalnum += events['inventory']['quantity'][index]
    if (not underground):
        while (totalnum < goal_num):
            trynum += 1
            delta = totalnum-prevnum
            if (delta == 0):
                explore_above_ground(object,underground,50)
            else:
                explore_above_ground(object,underground,10)
            prevnum = totalnum
            if (approach(object,underground)):  
                # pdb.set_trace()
                mine(object,equipment,underground)

            events = sleep(env)
            inventory = events['inventory']['name'].tolist()
            try:
                indices = [index for index, value in enumerate(inventory) if value == target_object]
            except ValueError:
                indices = []
                print(f"no object {target_object} found")
            if (indices):
                print(indices)
                events = sleep(env)
                totalnum = 0
                for index in indices:
                    totalnum += events['inventory']['quantity'][index]
            
            print(f"total number of {target_object} is {totalnum}, trynum is {trynum}")
    else:
        while (totalnum < goal_num):
            trynum += 1
            delta = totalnum-prevnum
            if (delta == 0):
                explore_above_ground(object,underground,50)
            else:
                explore_above_ground(object,underground,10)

            prevnum = totalnum  
            mine(object,equipment,underground)
            events = sleep(env)
            inventory = events['inventory']['name'].tolist()

            try:
                indices = [index for index, value in enumerate(inventory) if value == target_object]
            except ValueError:
                indices = []
                print(f"no object {target_object} found")
            if (indices):
                events = sleep(env)
                totalnum = 0
                for index in indices:
                    totalnum += events['inventory']['quantity'][index]

            print(f"total number of {target_object} is {totalnum}, trynum is {trynum}")
    mine_ahead(env,memory,)  # for craft
    # change back
    '''

# Function for mining a target with tools as specified by the parameter 'equipment'.
# Only to be used when agent is within mining distance of the target.
# Note that the target parameter in this function and the object parameter in action_mine may not be the same!(difference between wood and log)
# Target parameter is the object's name in the voxel array, object parameter is the object's name in inventory.
def mine(target,equipment,underground,env,memory):
    print(f"executing mining of {target} with {equipment}")
    events  = sleep(env)
    global dontstop
    old_target = target
    if(target=="log"):
        target="wood"
    elif target == "cobblestone":
        target = "stone"
    elif target =="diamond":
        target = "diamond ore"

    # cb_inventory_index = events['inventory']['name'].tolist().index(equipment)  #################for debug, could be changed
    # events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events)
    # if (np.isin(target,events['rays']['block_name']) or np.isin(object,events['rays']['entity_name'])):
    #     block_within_range = 1
    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); 
    share_memory(memory,events)
    
    inventory = events['inventory']['name'].tolist()
    #print(f"mine()----inventory")
    try:
        cb_inventory_index = inventory.index(equipment)
    except ValueError:
        cb_inventory_index = -1 
        print(f"no equipment {equipment} found222222222")
    if (cb_inventory_index != -1):
        events = sleep(env)
        events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip tool
    print(f"found equipment {equipment}")

    def inventory_quantity(current_events, item_name):
        total = 0
        for name, quantity in zip(
            current_events['inventory']['name'].tolist(),
            current_events['inventory']['quantity'].tolist(),
        ):
            if name == item_name:
                total += quantity
        return total

    inventory_target_name = update_inventory_obj_name(old_target)
    initial_target_quantity = inventory_quantity(events, inventory_target_name)

    def bounded_attack_until_voxel_changes(current_events, still_target, direction_label, max_hits=12):
        """Mine one adjacent underground voxel without an unbounded attack loop."""
        for _ in range(max_hits):
            if not still_target(current_events):
                return current_events, True
            current_events, _, _, _ = env.step([0,0,0,12,12,3,0,0])
            save_rgb_for_video(current_events)
        cleared = not still_target(current_events)
        if not cleared:
            print(f"underground mining exhausted {max_hits} hits at {direction_label}")
        return current_events, cleared

    def mine_adjacent_target(events, block_name):
        # Prefer deterministic close-range mining before relying on ray casts.
        adjacent_offsets = [
            ((vradius+1, vradius+1, vradius), (12, 12)),
            ((vradius+1, vradius, vradius), (15, 12)),
            ((vradius+1, vradius+2, vradius), (6, 12)),
            ((vradius, vradius+1, vradius+1), (12, 18)),
            ((vradius, vradius, vradius+1), (15, 18)),
            ((vradius, vradius+2, vradius+1), (6, 18)),
            ((vradius, vradius+1, vradius-1), (12, 6)),
            ((vradius, vradius, vradius-1), (15, 6)),
            ((vradius, vradius+2, vradius-1), (6, 6)),
            ((vradius+1, vradius+1, vradius+1), (10, 18)),
            ((vradius+1, vradius, vradius+1), (15, 18)),
            ((vradius+1, vradius+2, vradius+1), (6, 18)),
            ((vradius+1, vradius+1, vradius-1), (10, 6)),
            ((vradius+1, vradius, vradius-1), (15, 6)),
            ((vradius+1, vradius+2, vradius-1), (6, 6)),
            ((vradius, vradius+2, vradius), (6, 12)),
            ((vradius, vradius-1, vradius), (18, 12)),
        ]
        for (x_idx, y_idx, z_idx), (pitch, yaw) in adjacent_offsets:
            if events['voxels']['block_name'][x_idx][y_idx][z_idx] != block_name:
                continue
            events,_,_,_ = env.step([0,0,0,pitch,yaw,0,0,0]); save_rgb_for_video(events)
            success = False
            for _ in range(6):
                events,_,_,_ = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
                if np.isin(old_target, events["delta_inv"]["inc_name_by_other"]) or inventory_quantity(events, inventory_target_name) > initial_target_quantity:
                    success = True
                    break
            if success:
                print("mining successful via adjacent voxel")
                return events, True
        return events, False

    def mine_local_target(events, block_name):
        candidate_offsets = []
        for x_idx in range(vradius - 1, vradius + 3):
            for y_idx in range(vradius - 1, vradius + 3):
                for z_idx in range(vradius - 1, vradius + 3):
                    if not (0 <= x_idx < events['voxels']['block_name'].shape[0]):
                        continue
                    if not (0 <= y_idx < events['voxels']['block_name'].shape[1]):
                        continue
                    if not (0 <= z_idx < events['voxels']['block_name'].shape[2]):
                        continue
                    if events['voxels']['block_name'][x_idx][y_idx][z_idx] != block_name:
                        continue
                    forward_offset = x_idx - vradius
                    vertical_offset = y_idx - vradius
                    side_offset = z_idx - vradius
                    distance = abs(forward_offset) + abs(vertical_offset) + abs(side_offset)
                    candidate_offsets.append((
                        distance,
                        abs(forward_offset - 1),
                        abs(side_offset),
                        abs(vertical_offset),
                        x_idx,
                        y_idx,
                        z_idx,
                    ))

        candidate_offsets.sort()
        for _, _, _, _, x_idx, y_idx, z_idx in candidate_offsets[:8]:
            pitch = int(np.clip(12 - 3 * (y_idx - (vradius + 1)), 6, 18))
            yaw = int(np.clip(12 + 6 * (z_idx - vradius), 0, 24))
            events,_,_,_ = env.step([0,0,0,pitch,yaw,0,0,0]); save_rgb_for_video(events)
            success = False
            for _ in range(12):
                events,_,_,_ = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
                if np.isin(old_target, events["delta_inv"]["inc_name_by_other"]) or inventory_quantity(events, inventory_target_name) > initial_target_quantity:
                    success = True
                    break
            if success:
                print("mining successful via local voxel targeting")
                return events, True
        return events, False

    if not underground:
        events, close_success = mine_adjacent_target(events, target)
        if close_success:
            print(f"Present inventory:{events['inventory']['name']}")
            print(f"Present inventory:{events['inventory']['quantity']}")
            name = events['inventory']['name'].tolist()
            num = events['inventory']['quantity'].tolist()
            return name, num

        if target == "wood":
            events, local_success = mine_local_target(events, target)
            if local_success:
                print(f"Present inventory:{events['inventory']['name']}")
                print(f"Present inventory:{events['inventory']['quantity']}")
                name = events['inventory']['name'].tolist()
                num = events['inventory']['quantity'].tolist()
                return name, num

        loopnum = 2
        for i in range (loopnum):
           # print(f"rays_blocks_name is {target,events['rays']['block_name']}")
            if np.isin(target,events['rays']['block_name']):
                indices = np.where(events['rays']['block_name'] == target)[0]
                positions = [indices[0]]
                pos = positions[0]
                for idx in indices:
                    if events['rays']['block_distance'][idx]<3:
                        pos = idx
                        break
                print(f"{len(positions)}  positions found")
                if (positions):
                    observation = ""
                    for i in range(events['voxels']['block_name'].shape[0]):
                        for j in range(events['voxels']['block_name'].shape[1]):
                            for k in range(events['voxels']['block_name'].shape[2]):
                                # Convert the element to a string and append it to 'observation'
                                observation += str(events['voxels']['block_name'][i, j, k]) + " "
                            observation+='\n'
                        observation +='\n'
                    # print (observation)
               # print(f"pos is {pos}")
                quotient, remainder = divmod(pos+1, 25)
                #print(f"quotient is {quotient}")
                xangle, remainder_ = divmod((13-remainder),3)
                #print(f"xangle is {xangle}")
                # if (remainder_ == 2):
                #     xangle += 1
                xangle -= 1# notsure
                yangle,remainder_ = divmod((13-quotient),3)
                #print(f"yangle is {yangle}")
            
                # if (remainder_ == 2):
                #     yangle += 1
                yangle -= 1# notsure
                events,_,_,_ = env.step([0,0,0,12,12+xangle,0,0,0]); save_rgb_for_video(events)
                #events,_,_,_ = env.step([0,0,0,12,12+xangle,0,0,0]); save_rgb_for_video(events)
                
                events,_,_,_ = env.step([0,0,0,12+yangle,12,0,0,0]); save_rgb_for_video(events)
                #events,_,_,_ = env.step([0,0,0,12+yangle,12,0,0,0]); save_rgb_for_video(events)
                flag = 0
                for i in range(3):
                    events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
                    if np.isin(old_target, events["delta_inv"]["inc_name_by_other"]) or inventory_quantity(events, inventory_target_name) > initial_target_quantity:
                        flag = 1
                        break
                    # save_rgb_as_image(env,f"{i}")
                if (not flag):
                    dontstop = 1
                    print(f"mining UNsuccessful")
                    #explore_above_ground(env=env,args=args, object=find_obj, performer=self, memory=self.memory, task_information=task_information, underground=underground)
                else:
                    dontstop = 0
                    print(f"mining successful")
                    print(f"Present inventory:{events['inventory']['name']}")
                    print(f"Present inventory:{events['inventory']['quantity']}")
                    name = events['inventory']['name'].tolist()
                    num = events['inventory']['quantity'].tolist()
                    return name, num

                events,_,_,_ = env.step([0,0,0,12,13,0,0,0]); save_rgb_for_video(events)# turn slightly
                for i in range(3):
                    events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
                    # save_rgb_as_image(env,f"again{i}")
                events,_,_,_ = env.step([0,0,0,12,11,0,0,0]); save_rgb_for_video(events)# recover from slight turn
                events,_,_,_ = env.step([0,0,0,12,12-xangle,0,0,0]); save_rgb_for_video(events)
                events,_,_,_ = env.step([0,0,0,12-yangle,12,0,0,0]); save_rgb_for_video(events)# return to initial angle
                # positions = []
                # indices = np.where(events['rays']['block_name'] == target)[0]
                # for idx in indices:
                #     if events['rays']['block_distance'][idx] < 3:
                #         # smallest_element = events['rays']['block_distance'][idx]
                #         positions.append(idx)
                # if (positions):
                #     block_within_range = 1
                # else:
                #     block_within_range = 0
                    
            elif np.isin(object,events['rays']['entity_name']):
                #print(f"target is{target},{events['rays']['entity_name'] }")
                indices = np.where(events['rays']['entity_name'] == target)[0]
                smallest_element = 100
                pos = indices[0]
                # for idx in indices:
                #     if events['rays']['entity_distance'][idx] < smallest_element:
                #         smallest_element = events['rays']['entity_distance'][idx]
                #         pos = idx
                quotient, remainder = divmod(pos+1, 25)
                xangle, remainder = divmod((13-remainder),3)
                yangle,remainder = divmod((13-quotient),3)
                events,_,_,_ = env.step([0,0,0,12,12+xangle,0,0,0]); save_rgb_for_video(events)
                events,_,_,_ = env.step([0,0,0,12+yangle,12,0,0,0]); save_rgb_for_video(events)
                for i in range(10):
                    events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
                    # save_rgb_as_image(env,f"{i}")
                events,_,_,_ = env.step([0,0,0,12,13,0,0,0]); save_rgb_for_video(events)# turn slightly
                for i in range(10):
                    events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
                    # save_rgb_as_image(env,f"again{i}")
                events,_,_,_ = env.step([0,0,0,12,11,0,0,0]); save_rgb_for_video(events)# recover from slight turn
                events,_,_,_ = env.step([0,0,0,12,12-xangle,0,0,0]); save_rgb_for_video(events)
                events,_,_,_ = env.step([0,0,0,12-yangle,12,0,0,0]); save_rgb_for_video(events)# return to initial angle
            else:
                print("not in range")

              
                # save_rgb_as_image(env,"not_in_range")
        # mine_around(object,equipment)

        print(f"Present inventory:{events['inventory']['name']}")
        print(f"Present inventory:{events['inventory']['quantity']}")
    else:
        events = sleep(env)
        # right down
        if (events['voxels']['block_name'][vradius][vradius][vradius+1]==target):
            events,_,_,_ = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
            events,_,_,_ = env.step([0,0,0,15,12,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius][vradius][vradius+1] == target, "right-down"
            )
            events,_,_,_ = env.step([0,0,0,9,12,0,0,0]); save_rgb_for_video(events)
            events,_,_,_ = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
            sleep(env)
        # right top
        if (events['voxels']['block_name'][vradius][vradius+1][vradius+1]==target):
            events,_,_,_ = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius][vradius+1][vradius+1] == target, "right-top"
            )
            events,_,_,_ = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
            sleep(env)
        # forward down
        if (events['voxels']['block_name'][vradius+1][vradius][vradius]==target):
            events,_,_,_ = env.step([0,0,0,15,12,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius+1][vradius][vradius] == target, "forward-down"
            )
            events,_,_,_ = env.step([0,0,0,9,12,0,0,0]); save_rgb_for_video(events)
            sleep(env)
        # forward top
        if (events['voxels']['block_name'][vradius+1][vradius+1][vradius]==target):
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius+1][vradius+1][vradius] == target, "forward-top"
            )
            sleep(env)
        # left down
        if (events['voxels']['block_name'][vradius][vradius][vradius-1]==target):
            events,_,_,_ = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
            events,_,_,_ = env.step([0,0,0,15,12,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius][vradius][vradius-1] == target, "left-down"
            )
            events,_,_,_ = env.step([0,0,0,9,12,0,0,0]); save_rgb_for_video(events)
            events,_,_,_ = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
            sleep(env)
        # left top
        if (events['voxels']['block_name'][vradius][vradius+1][vradius-1]==target):
            events,_,_,_ = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius][vradius+1][vradius-1] == target, "left-top"
            )
            events,_,_,_ = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
            sleep(env)
        # top
        if (events['voxels']['block_name'][vradius][vradius+2][vradius]==target):
            events,_,_,_ = env.step([0,0,0,6,12,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius][vradius+2][vradius] == target, "top"
            )
            events,_,_,_ = env.step([0,0,0,18,12,0,0,0]); save_rgb_for_video(events)
            sleep(env)
        # down
        if (events['voxels']['block_name'][vradius][vradius-1][vradius]==target):
            events,_,_,_ = env.step([0,0,0,18,12,0,0,0]); save_rgb_for_video(events)
            events, _ = bounded_attack_until_voxel_changes(
                events, lambda current: current['voxels']['block_name'][vradius][vradius-1][vradius] == target, "down"
            )
            events,_,_,_ = env.step([0,0,0,6,12,0,0,0]); save_rgb_for_video(events)
            sleep(env)

    mine_ahead(env,memory)   
    events = sleep(env)

     # equipe dirt 
    '''
    inventory = events['inventory']['name'].tolist()
    try:
        cb_inventory_index = inventory.index('dirt')
    except ValueError:
        cb_inventory_index = -1 
        print(f"no equipment dirt found")
    if (cb_inventory_index != -1):
        events = sleep(env)
        events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip tool
    '''
    name = events['inventory']['name'].tolist()
    num = events['inventory']['quantity'].tolist()

    return name, num

# A function that enables agent to clear itself of obstacles in front of him,
# ONLY TO BE USED WHEN AGENT IS ABOVE GROUND! (as it is pretty destructive and does not gauge the extent of destruction until the function is finished)
def mine_ahead_aboveground(env):
    print('trying to mine ahead')
    for i in range(5):
        events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)# mine ahead

    events,reward,ended,addinfo = env.step([0,0,0,10,12,0,0,0]); save_rgb_for_video(events)
    for i in range(5):
        events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)# mine 30 degrees upwards
    events,reward,ended,addinfo = env.step([0,0,0,8,12,0,0,0]); save_rgb_for_video(events)
    for i in range(5):
        events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)# mine above head
    events,reward,ended,addinfo = env.step([0,0,0,18,12,0,0,0]); save_rgb_for_video(events)

    # events,reward,ended,addinfo = env.step([0,0,0,15,12,0,0,0]); save_rgb_for_video(events)
    # for i in range(3):
    #     events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)# mine 45 degree downwards
    # events,reward,ended,addinfo = env.step([0,0,0,9,12,0,0,0]); save_rgb_for_video(events)

    events,reward,ended,addinfo = env.step([0,0,0,12,13,0,0,0]); save_rgb_for_video(events)
    for i in range(5):
        events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)# mine left 15 degrees
    events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)
    for i in range(5):
        events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)# mine right 15 degrees
    events,reward,ended,addinfo = env.step([0,0,0,12,13,0,0,0]); save_rgb_for_video(events)

# A function that mines the two blocks right in front of the agent's body and head to form a tunnel for passage.
# Did not check implementation, may have to rewrite and modify.
# Currently this function is only used when agent is exploring under ground.
# Agent facing north -> direction = 0; Agent facing west -> direction = 1; 
# Agent facing east -> direction = 2; Agent facing south -> direction = 3; 
######## only refine direction=0, other to be done
def mine_ahead(env, memory, direction=0, max_hits=12):
    """Clear the body/head blocks in one direction with a finite attack budget.

    Returns ``True`` only when both target blocks are clear.  Callers can therefore
    choose recovery rather than assuming that a failed clearance opened a passage.
    """
    if isinstance(max_hits, bool) or not isinstance(max_hits, int) or max_hits <= 0:
        raise ValueError("max_hits must be a positive integer")
    if direction not in {0, 1, 2, 3}:
        raise ValueError("direction must be one of 0, 1, 2, or 3")

    events, _, _, _ = env.step([0, 0, 0, 12, 12, 0, 0, 0])
    share_memory(memory, events)
    events = sleep(env)
    print("trying to mine")
    print(f"mine_ahead:{memory.inventory}")

    def bounded_attack_until(clear_check, look_action=None):
        nonlocal events
        if look_action is not None:
            events, _, _, _ = env.step(look_action)
            save_rgb_for_video(events)
        for _ in range(max_hits):
            if clear_check(events):
                return True
            events, _, _, _ = env.step([0, 0, 0, 12, 12, 3, 0, 0])
            save_rgb_for_video(events)
        return clear_check(events)

    if events["location_stats"]["pos"][1] < 20:
        inventory = events["inventory"]["name"].tolist()
        try:
            pickaxe_index = inventory.index("iron pickaxe")
        except ValueError:
            pickaxe_index = -1
            print("no equipment iron pickaxe found")
        if pickaxe_index != -1:
            events = sleep(env)
            events, _, _, _ = env.step([0, 0, 0, 12, 12, 5, 0, pickaxe_index])
            save_rgb_for_video(events)

    if direction == 0:
        head_clear = lambda e: e["voxels"]["block_name"][vradius + 1][vradius + 1][vradius] in ("air", "water")
        body_clear = lambda e: e["voxels"]["block_name"][vradius + 1][vradius][vradius] in ("air", "water")
        body_look, restore_look = [0, 0, 0, 15, 12, 0, 0, 0], [0, 0, 0, 9, 12, 0, 0, 0]
    elif direction == 1:
        head_clear = lambda e: e["voxels"]["block_name"][vradius][vradius + 1][vradius - 1] in ("air", "water")
        body_clear = lambda e: e["voxels"]["block_name"][vradius][vradius][vradius - 1] in ("air", "water")
        body_look, restore_look = [0, 0, 0, 10, 12, 0, 0, 0], [0, 0, 0, 14, 12, 0, 0, 0]
    elif direction == 2:
        head_clear = lambda e: e["voxels"]["block_name"][vradius][vradius + 1][vradius + 1] in ("air", "water")
        body_clear = lambda e: e["voxels"]["block_name"][vradius][vradius][vradius + 1] in ("air", "water")
        body_look, restore_look = [0, 0, 0, 10, 12, 0, 0, 0], [0, 0, 0, 14, 12, 0, 0, 0]
    else:
        head_clear = lambda e: e["voxels"]["block_name"][vradius - 1][vradius + 1][vradius] in ("air", "water")
        body_clear = lambda e: e["voxels"]["block_name"][vradius - 1][vradius][vradius] in ("air", "water")
        body_look, restore_look = [0, 0, 0, 10, 12, 0, 0, 0], [0, 0, 0, 14, 12, 0, 0, 0]

    if head_clear(events) and body_clear(events):
        return True

    head_cleared = bounded_attack_until(head_clear)
    body_cleared = bounded_attack_until(body_clear, look_action=body_look)
    events, _, _, _ = env.step(restore_look)
    save_rgb_for_video(events)
    cleared = head_cleared and body_cleared
    if not cleared:
        print(f"mine_ahead exhausted {max_hits} hits without clearing direction {direction}")
    return cleared


# Function enabling the agent to move one block. Underground specifies if agent is underground or not.
# The direction parameter should fall within [0,3], 0: ahead along the positive direction of the x axis, 1: left, 2: right, 3: backward
# Regardless of whether agent is aboveground, agent will always WALK when jumpornot = 0.
# Jumpornot = 1 when underground = 0: agent will jump towards the given direction instead of walking.
# Jumpornot = 1 when underground = 1: agent will utilize mine_ahead to mine its way towards the given direction instead of walking.
def move_one_block(env,memory,movedir=0,underground=0,jumpornot = 0):
    if underground:
        print(f"MOVEONEBLOCK: movedir is {movedir}, underground is {underground}, jumpornot is {jumpornot}")
    global explore_steps
    events  = sleep(env)
    # print(f"move one block in direction {movedir} ; whether it is necessary to jump:{jumpornot}\n")
    if (underground == 0):
        start_pos = np.array(events['location_stats']['pos'], dtype=float)

        def moved_enough(current_pos):
            if movedir == 0:
                return current_pos[0] - start_pos[0] >= 0.45
            if movedir == 1:
                return start_pos[2] - current_pos[2] >= 0.45
            if movedir == 2:
                return current_pos[2] - start_pos[2] >= 0.45
            return start_pos[0] - current_pos[0] >= 0.45

        def aboveground_step():
            if movedir == 0:
                return [1,0,1 if jumpornot else 0,12,12,0,0,0]
            if movedir == 1:
                return [0,1,1 if jumpornot else 0,12,12,0,0,0]
            if movedir == 2:
                return [0,2,1 if jumpornot else 0,12,12,0,0,0]
            return [2,0,1 if jumpornot else 0,12,12,0,0,0]

        no_progress_steps = 0
        for _ in range(16):
            prev_pos = np.array(events['location_stats']['pos'], dtype=float)
            events,_,_,_ = env.step(aboveground_step()); save_rgb_for_video(events)
            current_pos = np.array(events['location_stats']['pos'], dtype=float)

            if moved_enough(current_pos):
                action_tuple = (movedir, jumpornot)
                if movedir == 0 or movedir == 2:
                    action_stack.append(action_tuple)
                return True

            if np.allclose(prev_pos, current_pos):
                no_progress_steps += 1
            else:
                no_progress_steps = 0

            if no_progress_steps >= 2:
                return False

        return False
    else:
        if ( not jumpornot):
            if (movedir == 0):
                try_num = 0    
                while (events['location_stats']['pos'][0]<math.ceil(events['location_stats']['pos'][0])+0.45):
                    if (try_num > 20):
                        return False
                    try_num += 1
                    events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # print(f"present x is {events['location_stats']['pos'][0]} and it should be larger than {math.floor(events['location_stats']['pos'][0])+0.44}")
            elif (movedir == 2):# right
                try_num = 0
                while (events['location_stats']['pos'][0]>math.floor(events['location_stats']['pos'][0])-0.45):
                    if (try_num > 20):
                        return False
                    try_num += 1
                    events,_,_,_ = env.step([0,2,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            elif (movedir == 1):# left
                try_num = 0
                while (events['location_stats']['pos'][2]<math.ceil(events['location_stats']['pos'][2])+0.45):
                    if (try_num > 10):
                        return False
                    try_num += 1
                    events,_,_,_ = env.step([0,1,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            else:
                try_num = 0
                while (events['location_stats']['pos'][2]>math.floor(events['location_stats']['pos'][0])-0.45):
                    if (try_num > 20):
                        return False
                    try_num += 1
                    events,_,_,_ = env.step([2,0,0,12,12,0,0,0]); save_rgb_for_video(events)  
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)      
        else:
      
            if (movedir == 0):
                try_num = 0    
                mine_ahead(env,memory,0)
                while (events['location_stats']['pos'][0]<math.ceil(events['location_stats']['pos'][0])+0.45):
                    if (try_num > 10):
                        return False
                    try_num += 1
                    # mine_ahead(env,0)
                    events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # print(f"present x is {events['location_stats']['pos'][0]} and it should be larger than {math.floor(events['location_stats']['pos'][0])+0.44}")
            elif (movedir == 2):# right
                events,reward,ended,addinfo = env.step([0,0,0,12,14,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,14,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,14,0,0,0]); save_rgb_for_video(events)
                mine_ahead(env,memory,2)
                try_num = 0
                while (events['location_stats']['pos'][0]>math.floor(events['location_stats']['pos'][0])-0.45):
                    if (try_num > 10):
                        return False
                    try_num += 1
                    events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)

                
            elif (movedir == 1):# left
                events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,10,0,0,0]); save_rgb_for_video(events)
                mine_ahead(env,memory,1)
                try_num = 0
                while (events['location_stats']['pos'][2]<math.ceil(events['location_stats']['pos'][2])+0.45):
                    if (try_num > 10):
                        return False
                    try_num += 1
                    events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,14,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,14,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,14,0,0,0]); save_rgb_for_video(events)
                
            else:
                events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
                try_num = 0
                while (events['location_stats']['pos'][2]>math.floor(events['location_stats']['pos'][0])-0.45):
                    if (try_num > 10):
                        return False
                    try_num += 1
                    mine_ahead(env,memory,3)
                    events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    # events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)  
                events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
                events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
                
        action_tuple = (movedir, jumpornot)
        if movedir == 0 or movedir == 2:
            action_stack.append(action_tuple)
        return True


# This function decides whether agent can reach block ahead of him.
# If agent can reach the block ahead of him, he will call the function move_one_block and move ahead, returning true.
# If not, the function will return false and the agent will do nothing.
# Both explore_above_ground and approach call this function, the approach parameter will tell the function
# whether the function is called in explore or approach. It is necessary to distinguish between the 
# two scenarios as the agent has very different standards of path accessibility in the two cases.
# In approach, try_forward will nearly always return true as agent is desperate to get to target object.
def try_forward(env,memory,underground,approach=0):
    events  = sleep(env)
    print(f"explore_steps is {explore_steps}, front floor is {events['voxels']['block_name'][vradius+1][vradius-1][vradius]}, block in front of body is {events['voxels']['block_name'][vradius+1][vradius][vradius]}, in front of head is {events['voxels']['block_name'][vradius+1][vradius+1][vradius]}")
    if (approach and (not underground)):
        events = sleep(env)
        if (events['voxels']['block_name'][vradius+1][vradius][vradius] == "water"):
            move_one_block(env,memory,0,0,1)
        elif (events['voxels']['block_name'][vradius+1][vradius+1][vradius] not in ("lava", "air")):
            print(f"approaching and met with obstacle , have to mine")
            move_to_middle(env)
            mine_ahead_aboveground(env)
            prev_pos = events['location_stats']['pos']
            move_one_block(env,memory,0,0,1)
            pres_pos = events['location_stats']['pos']
            are_equal = (prev_pos == pres_pos).all()
            if are_equal:
                return False # return false only if agent finds itself stuck
            return True
        else:
            move_one_block(env,memory,0,0,1)
            return True
    if (not underground):
        if (events['voxels']['block_name'][vradius+1][vradius-1][vradius] != "air") and events['voxels']['block_name'][vradius+1][vradius][vradius]== "air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air":
            if (events['voxels']['block_name'][vradius+1][vradius-1][vradius] != "lava"):
                move_one_block(env,memory,0,0,0)
                return True
            else:
                print(f"lava")
                return False
        elif (events['voxels']['block_name'][vradius+1][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius+1][vradius][vradius]=="water" or events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="water" or events['voxels']['block_name'][vradius+1][vradius+2][vradius]=="water" or events['voxels']['block_name'][vradius][vradius+1][vradius]=="water"):
            move_one_block(env,memory,0,0,1)
            return True
        elif (events['voxels']['block_name'][vradius+1][vradius][vradius]!="air" and events['voxels']['block_name'][vradius+1][vradius][vradius] != "lava") and events['voxels']['block_name'][vradius+1][vradius+1][vradius]== "air" and events['voxels']['block_name'][vradius+1][vradius+2][vradius]=="air":
            print("can jump one block to move ahead\n")
            move_one_block(env,memory,0,0,1)
            return True
        elif (events['voxels']['block_name'][vradius+1][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius+1][vradius][vradius]=="water"):
            move_one_block(env,memory,0,0,1)# jump if water is a head of you
        else:
            no_climb = True
            for i in range(2):
                if (events['voxels']['block_name'][vradius+1][vradius+i][vradius]=="air"):
                    continue
                else:
                    no_climb=False
                    break
            if (no_climb):
                no_footing = True
                for i in range(vradius - 1, -1, -1):#cgd
                    if (events['voxels']['block_name'][vradius+1][i][vradius]=="lava"):#cgd
                        print(f"can't move because of lava")
                        return False
                    if (events['voxels']['block_name'][vradius+1][i][vradius]=="air"):
                        continue
                    else:
                        no_footing = False
                        break
                if no_footing:
                    return True
                else:
                    move_one_block(env,memory,0,0,0)
                    return True
            print(f"can't move because of climb")
            return False
    else:
        if (events['voxels']['block_name'][vradius+1][vradius-1][vradius] not in ("lava", "water")) and events['voxels']['block_name'][vradius+1][vradius][vradius]== "air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air":
            if (events['voxels']['block_name'][vradius+2][vradius-1][vradius] != "water" and events['voxels']['block_name'][vradius+2][vradius][vradius] != "water" and events['voxels']['block_name'][vradius+2][vradius+1][vradius] != "water" and events['voxels']['block_name'][vradius+2][vradius+2][vradius] != "water" and events['voxels']['block_name'][vradius+2][vradius+3][vradius] != "water"):
                move_one_block(env,memory,0,0,0)
                return True
            else:
                return False
        if (events['voxels']['block_name'][vradius+1][vradius-1][vradius] not in ("air", "water")) and events['voxels']['block_name'][vradius+1][vradius][vradius]== "air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air":
            if (events['voxels']['block_name'][vradius+1][vradius-1][vradius] != "lava"):
                move_one_block(env,memory,0,0,0)
                return True
            else:
                return False
        elif ((events['voxels']['block_name'][vradius+1][vradius-1][vradius] in ("lava", "water")) or events['voxels']['block_name'][vradius+1][vradius][vradius] in ("lava", "water") or events['voxels']['block_name'][vradius+1][vradius+1][vradius] in ("lava", "water")) or events['voxels']['block_name'][vradius+2][vradius-1][vradius] in ("lava", "water") or events['voxels']['block_name'][vradius+2][vradius][vradius] in ("lava", "water") or events['voxels']['block_name'][vradius+2][vradius+1][vradius] in ("lava", "water"):
            return False# lava right in front of you
        elif ((events['voxels']['block_name'][vradius+1][vradius-1][vradius]!="lava") and events['voxels']['block_name'][vradius+1][vradius][vradius] != "lava" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]!="lava"):
            move_one_block(env,memory,0,1,1)#solid blocks ahead, have to mine them
        
        else:
            no_climb = True
            for i in range(2):
                if (events['voxels']['block_name'][vradius+1][vradius-1+i][vradius]=="air"):
                    continue
                else:
                    no_climb=False
                    break
            if (no_climb):
                no_footing = True
                for i in range(vradius - 1, -1, -1):#cgd
                    if (events['voxels']['block_name'][vradius+1][i][vradius]=="lava"):#cgd
                        return False
                    if (events['voxels']['block_name'][vradius+1][i][vradius]=="air"):
                        continue
                    else:
                        no_footing = False
                        break
                if no_footing:
                    return False
                else:
                    move_one_block(env,memory,0,0,0)
                    return True
            return False

# This function decides whether agent can reach block behind him.
# If agent can reach the block, he will call the function move_one_block and move backwards, returning true.
# If not, the function will return false and the agent will do nothing.
# TRY_BACKWARD is implemented very CRUDELY, feel free to modify and rewrite.
def try_backward(env,memory,underground):# tbd: have to complete and may probably be made better use of
    events  = sleep(env)
    print(f"blocks behind: are {events['voxels']['block_name'][vradius-1][vradius-1][vradius]}, {events['voxels']['block_name'][vradius-1][vradius][vradius]},{events['voxels']['block_name'][vradius-1][vradius-1][vradius]}")
    if (events['voxels']['block_name'][vradius-1][vradius-1][vradius] not in ("air", "water")) and events['voxels']['block_name'][vradius-1][vradius][vradius]== "air" and events['voxels']['block_name'][vradius-1][vradius+1][vradius]=="air":
        if (events['voxels']['block_name'][vradius-1][vradius-1][vradius] != "lava"):
            move_one_block(env,memory,3,0,0)
            return True
        else:
            return False
    elif (events['voxels']['block_name'][vradius-1][vradius][vradius]!="air" and events['voxels']['block_name'][vradius-1][vradius][vradius] != "lava") and events['voxels']['block_name'][vradius-1][vradius+1][vradius]== "air" and events['voxels']['block_name'][vradius-1][vradius+2][vradius]=="air":
        print("can jump one block to backward\n")
        move_one_block(env,memory,3,0,1)
        return True
    else:
        no_climb = True
        for i in range(2):
            if (events['voxels']['block_name'][vradius-1][vradius+i][vradius]=="air"):
                continue
            else:
                no_climb=False
                break
        if (no_climb):
            no_footing = True
            for i in range(vradius - 1, -1, -1):#cgd
                if (events['voxels']['block_name'][vradius-1][i][vradius]=="lava"):#cgd
                    return False
                if (events['voxels']['block_name'][vradius-1][i][vradius]=="air"):
                    continue
                else:
                    no_footing = False
                    break
            if no_footing:
                return False
            else:
                move_one_block(env,memory,3,0,0)
                return True
        return False
    

# This function decides whether agent can reach block on his left.
# If agent can reach the block, he will call the function move_one_block and move leftwards, returning true.
# If not, the function will return false and the agent will do nothing.
def try_leftward(env,memory,underground,approach = 0):
    events  = sleep(env)
    # create_observation(env,"leftward_approach")
    if (approach):
        start_pos = np.array(events['location_stats']['pos'], dtype=float)
        if events['voxels']['block_name'][vradius][vradius+1][vradius-1]!= "air" :
            # if (events['voxels']['block_name'][vradius][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius][vradius][vradius]=="water"):
            #     return False
            # else:
            print(f"mining to walk left in approach")
            observation = ""
            for i in range(events['voxels']['block_name'].shape[0]):
                for j in range(events['voxels']['block_name'].shape[1]):
                    for k in range(events['voxels']['block_name'].shape[2]):
                        # Convert the element to a string and append it to 'observation'
                        observation += str(events['voxels']['block_name'][i, j, k]) + " "
                    observation+='\n'
                observation +='\n'
            # print(f"have to mine because of observation:{observation}")
            events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
            mine_ahead_aboveground(env)
            events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
            moved = move_one_block(env,memory,1,0,0)
            events = sleep(env)
            return bool(moved and (start_pos[2] - events['location_stats']['pos'][2] >= 0.20))
        else:
            if events['voxels']['block_name'][vradius][vradius+2][vradius-1]== "air" and events['voxels']['block_name'][vradius][vradius+2][vradius]== "air":
               # print(f"jumping leftward-before--------present position is {events['location_stats']['pos']}")
                moved = move_one_block(env,memory,1,0,1)
                events = sleep(env)
                #print(f"jumping leftward-before--------present position is {events['location_stats']['pos']}")
                return bool(moved and (start_pos[2] - events['location_stats']['pos'][2] >= 0.20))
            elif (events['voxels']['block_name'][vradius][vradius][vradius-1]!= "air"):
                events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
                mine_ahead_aboveground(env)
                events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
                moved = move_one_block(env,memory,1,0,0)
                events = sleep(env)
                print("walking rightward")
                return bool(moved and (start_pos[2] - events['location_stats']['pos'][2] >= 0.20))
            return False
    if (underground):
        # print(f"explore_steps is {explore_steps}, front floor is {events['voxels']['block_name'][vradius][vradius-1][vradius+1]}, block in front of body is {events['voxels']['block_name'][vradius][vradius][vradius]}, in front of head is {events['voxels']['block_name'][vradius+1][vradius+1][vradius]}")
        if (events['voxels']['block_name'][vradius][vradius-1][vradius-1] not in ("air", "water")) and events['voxels']['block_name'][vradius][vradius][vradius-1]== "air" and events['voxels']['block_name'][vradius][vradius+1][vradius-1]=="air":
            if (events['voxels']['block_name'][vradius][vradius-1][vradius-1] != "lava"):
                move_one_block(env,memory,1,underground,0)
                return True 
            
        elif events['voxels']['block_name'][vradius][vradius][vradius-1] not in ("air", "lava") and events['voxels']['block_name'][vradius][vradius+1][vradius-1]!= "air" and events['voxels']['block_name'][vradius][vradius+2][vradius-1]!="air":
            # if (events['voxels']['block_name'][vradius][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius][vradius][vradius]=="water"):
            #     return False
            # else:
            observation = ""
            for i in range(events['voxels']['block_name'].shape[0]):
                for j in range(events['voxels']['block_name'].shape[1]):
                    for k in range(events['voxels']['block_name'].shape[2]):
                        # Convert the element to a string and append it to 'observation'
                        observation += str(events['voxels']['block_name'][i, j, k]) + " "
                    observation+='\n'
                observation +='\n'
            #print(f"have to mine because of observation:{observation}")
            move_one_block(env,memory,1,1,1)
            return True
        else:
            no_climb = True
            for i in range(2):
                if (events['voxels']['block_name'][vradius][vradius+i][vradius-1]=="air"):
                    continue
                else:
                    no_climb=False
                    break
            if (no_climb):
                no_footing = True
                for i in range(vradius - 1, -1, -1):
                    if (events['voxels']['block_name'][vradius][i][vradius-1]=="lava"):
                        return False
                    if (events['voxels']['block_name'][vradius][i][vradius-1]=="air"):
                        continue
                    else:
                        no_footing = False
                        break
                if no_footing:
                    return False
                else:
                    move_one_block(env,memory,1,underground,0)
                    return True
            return False
    else:
        if (events['voxels']['block_name'][vradius][vradius-1][vradius-1] != "lava") and events['voxels']['block_name'][vradius][vradius][vradius-1]== "air" and events['voxels']['block_name'][vradius][vradius+1][vradius-1]=="air":
            if (events['voxels']['block_name'][vradius][vradius-1][vradius-1] != "lava"):
                move_one_block(env,memory,1,underground,0)
                return True
        elif (events['voxels']['block_name'][vradius][vradius][vradius-1]!="air" and events['voxels']['block_name'][vradius][vradius][vradius-1]!="lava" ) and events['voxels']['block_name'][vradius][vradius+1][vradius-1]!= "air" and events['voxels']['block_name'][vradius][vradius+2][vradius-1]!="air":
            # if (events['voxels']['block_name'][vradius][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius][vradius][vradius]=="water"):
            #     return False
            # else:
                move_one_block(env,memory,1,underground,1)
                return True
        elif ((events['voxels']['block_name'][vradius][vradius-1][vradius-1] in ("lava", "water")) or events['voxels']['block_name'][vradius][vradius][vradius-1] in ("lava", "water") or events['voxels']['block_name'][vradius][vradius+1][vradius-1] in ("lava", "water"))or events['voxels']['block_name'][vradius][vradius-1][vradius-2] in ("lava", "water") or events['voxels']['block_name'][vradius][vradius][vradius-2] in ("lava", "water") or events['voxels']['block_name'][vradius][vradius+1][vradius-2] in ("lava", "water"):
            return False# lava right in front of you
        elif ((events['voxels']['block_name'][vradius][vradius-1][vradius-1]!="lava") and events['voxels']['block_name'][vradius][vradius][vradius-1] != "lava" and events['voxels']['block_name'][vradius][vradius+1][vradius-1]!="lava"):
            move_one_block(env,memory,1,1,1)#solid blocks ahead, have to mine them
        
        else:
            no_climb = True
            for i in range(2):
                if (events['voxels']['block_name'][vradius][vradius-1+i][vradius-1]=="air"):
                    continue
                else:
                    no_climb=False
                    break
            if (no_climb):
                no_footing = True
                for i in range(vradius - 1, -1, -1):
                    if (events['voxels']['block_name'][vradius][i][vradius-1]=="lava"):
                        return False
                    if (events['voxels']['block_name'][vradius][i][vradius-1]=="air"):
                        continue
                    else:
                        no_footing = False
                        break
                if no_footing:
                    return False
                else:
                    move_one_block(env,memory,1,0,0)
                    return True
            return False
        
# This function decides whether agent can reach block on his right.
# If agent can reach the block, he will call the function move_one_block and move rightwards, returning true.
# If not, the function will return false and the agent will do nothing.
def try_rightward(env,memory,underground,approach = 0):
    events  = sleep(env)
    # create_observation(env,"righward_approach")
    if (approach):
        start_pos = np.array(events['location_stats']['pos'], dtype=float)
        if events['voxels']['block_name'][vradius][vradius+1][vradius+1]!= "air" or events['voxels']['block_name'][vradius][vradius][vradius+1]!= "air" :
        #if events['voxels']['block_name'][vradius][vradius+1][vradius+1]!= "air" or events['voxels']['block_name'][vradius][vradius-1][vradius+1]!= "air" or events['voxels']['block_name'][vradius][vradius][vradius+1]!= "air":
               
            # if (events['voxels']['block_name'][vradius][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius][vradius][vradius]=="water"):
            #     return False
            # else:
                observation = ""
                for i in range(events['voxels']['block_name'].shape[0]):
                    for j in range(events['voxels']['block_name'].shape[1]):
                        for k in range(events['voxels']['block_name'].shape[2]):
                            # Convert the element to a string and append it to 'observation'
                            observation += str(events['voxels']['block_name'][i, j, k]) + " "
                        observation+='\n'
                    observation +='\n'
                #print(f"mine rightward because of observation:{observation}")
                events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
                mine_ahead_aboveground(env)
                events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
                moved = move_one_block(env,memory,2,0,0)
                events = sleep(env)
                return bool(moved and (events['location_stats']['pos'][2] - start_pos[2] >= 0.20))
        else:
            if events['voxels']['block_name'][vradius][vradius+2][vradius+1]== "air" and events['voxels']['block_name'][vradius][vradius+2][vradius]== "air":
            #if events['voxels']['block_name'][vradius][vradius-1][vradius+1]== "air" and events['voxels']['block_name'][vradius][vradius+2][vradius]== "air":
                #print(f"jumping rightward-before--------present position is {events['location_stats']['pos']}")
                moved = move_one_block(env,memory,2,0,1)
                events = sleep(env)
                #print(f"jumping rightward-after--------present position is {events['location_stats']['pos']}")
                return bool(moved and (events['location_stats']['pos'][2] - start_pos[2] >= 0.20))
            elif (events['voxels']['block_name'][vradius][vradius][vradius+1]!= "air"):
                events,reward,ended,addinfo = env.step([0,0,0,12,18,0,0,0]); save_rgb_for_video(events)
                mine_ahead_aboveground(env)
                events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)
                moved = move_one_block(env,memory,2,0,0)
                events = sleep(env)
                print(f"walking rightward")
                return bool(moved and (events['location_stats']['pos'][2] - start_pos[2] >= 0.20))
        return False
    if (not underground):
        if (events['voxels']['block_name'][vradius][vradius-1][vradius+1] not in ("air", "water")) and events['voxels']['block_name'][vradius][vradius][vradius+1]== "air" and events['voxels']['block_name'][vradius][vradius+1][vradius+1]=="air":
            if (events['voxels']['block_name'][vradius][vradius-1][vradius+1] != "lava"):
                move_one_block(env,memory,2,0,0)
                return True
        elif (events['voxels']['block_name'][vradius][vradius][vradius+1]!="air" and events['voxels']['block_name'][vradius][vradius][vradius+1] != "lava") and events['voxels']['block_name'][vradius][vradius+1][vradius+1]== "air" and events['voxels']['block_name'][vradius][vradius+2][vradius+1]=="air" and events['voxels']['block_name'][vradius][vradius+2][vradius]=="air":
            print("can jump one block to move rightward\n")
            move_one_block(env,memory,2,0,1)
            return True
        elif (events['voxels']['block_name'][vradius][vradius-1][vradius+1]=="water" or events['voxels']['block_name'][vradius][vradius][vradius+1]=="water"  or events['voxels']['block_name'][vradius][vradius+1][vradius]=="water"):
            move_one_block(env,memory,2,0,1)# jump if water is on your right
        elif  events['voxels']['block_name'][vradius][vradius+1][vradius+1]!= "air" :
            # if (events['voxels']['block_name'][vradius][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius][vradius][vradius]=="water"):
            #     return False
            # else:x
                return False
        else:
            no_climb = True
            if (no_climb):
                no_footing = True
                for i in range(vradius - 1, -1, -1):
                    if (events['voxels']['block_name'][vradius][i][vradius+1]=="lava"):
                        return False
                    if (events['voxels']['block_name'][vradius][i][vradius+1]=="air"):
                        continue
                    else:
                        no_footing = False
                        break
                if no_footing:
                    return False
                else:
                    move_one_block(env,memory,2,0,0)
                    return True
            return False
    else:
        if (events['voxels']['block_name'][vradius][vradius-1][vradius+1] != "lava") and events['voxels']['block_name'][vradius][vradius][vradius+1]== "air" and events['voxels']['block_name'][vradius][vradius+1][vradius+1]=="air":
            if (events['voxels']['block_name'][vradius][vradius-1][vradius+1] != "lava"):
                move_one_block(env,memory,2,1,0)
                return True
        elif (events['voxels']['block_name'][vradius][vradius][vradius+1]!="air" and events['voxels']['block_name'][vradius][vradius][vradius+1]!="lava" ) and events['voxels']['block_name'][vradius][vradius+1][vradius+1]== "air" and events['voxels']['block_name'][vradius][vradius+2][vradius+1]=="air":
            # if (events['voxels']['block_name'][vradius][vradius-1][vradius]=="water" or events['voxels']['block_name'][vradius][vradius][vradius]=="water"):
            #     return False
            # else:
                move_one_block(env,memory,2,1,1)
                return True
        elif ((events['voxels']['block_name'][vradius][vradius-1][vradius+1] in ("lava", "water")) or events['voxels']['block_name'][vradius][vradius][vradius+1] in ("lava", "water") or events['voxels']['block_name'][vradius][vradius+1][vradius+1] in ("lava", "water"))or events['voxels']['block_name'][vradius][vradius-1][vradius+2] in ("lava", "water") or events['voxels']['block_name'][vradius][vradius][vradius+2] in ("lava", "water") or events['voxels']['block_name'][vradius][vradius+1][vradius+2] in ("lava", "water"):
            return False# lava right in front of you
        elif ((events['voxels']['block_name'][vradius][vradius-1][vradius+1]!="lava") and events['voxels']['block_name'][vradius][vradius][vradius+1] != "lava" and events['voxels']['block_name'][vradius][vradius+1][vradius+1]!="lava"):
            move_one_block(env,memory,2,1,1)#solid blocks ahead, have to mine them
        
        else:
            no_climb = True
            for i in range(2):
                if (events['voxels']['block_name'][vradius][vradius-1+i][vradius+1]=="air"):
                    continue
                else:
                    no_climb=False
                    break
            if (no_climb):
                no_footing = True
                for i in range(vradius - 1, -1, -1):
                    if (events['voxels']['block_name'][vradius][i][vradius+1]=="lava"):
                        return False
                    if (events['voxels']['block_name'][vradius][i][vradius+1]=="air"):
                        continue
                    else:
                        no_footing = False
                        break
                if no_footing:
                    return False
                else:
                    move_one_block(env,memory,2,0,0)
                    return True
            return False
    
direction = 0
retry_times = 0
# the function name explore_above_ground may be misleading, it is actually a function
# which can be used both in above-ground and underground scenarios,
# set parameter underground to 0 if above ground, set it to 1 if underground.
# once the agent has explored max_try_steps number of steps, it will stop regardless of whether object is within range.
def explore_above_ground(env,args,object,underground,performer,memory,task_information,max_try_steps=10000):
    global explore_steps
    # events  = sleep(env)
    global stuck
    global direction
    global prev_position
    global retry_times
    global dontstop
    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
    print(f"exploring once, front floor{events['voxels']['block_name'][vradius+1][vradius-1][vradius]}\n block in front of body is {events['voxels']['block_name'][vradius+1][vradius][vradius]} \n and block in front of head is {events['voxels']['block_name'][vradius+1][vradius+1][vradius]}\n ")
    
    # # make sure you drop tool into inventory before exploring so as not to waste them
    # inventory = events['inventory']['name'].tolist()
    # cb_inventory_index = inventory.index('air')
    # events,_,_,_ = env.step([0,0,0,16,12,0,0,0]); save_rgb_for_video(events)
    # events = sleep(env)
    # events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip crafting tabsle
    if (not underground):
        find_time = int(0)
        for i in range(max_try_steps):
            #events,_,_,info= env.step([0,0,0,12,12,0,0,0]); 
            
           # print(f"old inventory is {memory.inventory}")
            #share_memory(memory,events)
            #print(f"new inventory is {memory.inventory}")
            #print(f"env.info is {info['inventory']}")
            print(f"try_steps: {i}")
            check_result = performer.check_action_preparation(env,"find",args,task_information,events)

            if check_result["success"]:
                            print("222")
                            return True
            stuck = 0
            if i >= 2 and dontstop == 1:
                dontstop = 0
            # create_observation(env,f"observation_{i}")
            print(f"try step is {i} and dir is {direction}")
            print(f"explore step is {explore_steps} and position is {events['location_stats']['pos']}")

            
            # if lidar_detect(env,object) and (i!=0 and dontstop == 0):
            # # if voxel_detect(env,object) and (i!=0 and dontstop == 0):
            #     print("Found object {object}!!!yay")
            #     return True
            print(f"find time is {find_time}")
            if find_time>=0:
                save_rgb_as_image(env,f"{find_time}")
                file_path = f"../images/{find_time}.jpg"
                
                memory.reset_current_environment_information()
                #find_result = percipient.perceive(task_information=task_information, find_obj=object, file_path=file_path)
                find_result=check_find(env,memory,object,underground)
                if find_result == True:
                    print("Find successfully!")
                    return True
                

            find_time+=1
            if explore_steps >= 10000 :
                print("explore steps exceed limit")
                explore_steps = 0
                return False
            
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            if (prev_position[0] != events['location_stats']['pos'][0]) or (prev_position[2] != events['location_stats']['pos'][2]):
                stuck = 0
            else:
                stuck += 1
            prev_position = events['location_stats']['pos']
    
            if stuck>0:
                print(f"stuck!!!")
                stuck = 0
                observation = ""
                for i in range(events['voxels']['block_name'].shape[0]):
                    for j in range(events['voxels']['block_name'].shape[1]):
                        for k in range(events['voxels']['block_name'].shape[2]):
                            # Convert the element to a string and append it to 'observation'
                            observation += str(events['voxels']['block_name'][i, j, k]) + " "
                        observation+='\n'
                    observation +='\n'
                # print(f"stuck observation:{observation}")
                mined_ahead = 0
                
                while (True):# an issue here
                    flag = False
                    if flag:
                        break
                    retry_times += 1
                    if (retry_times > 2):
                        observation = ""
                        for i in range(events['voxels']['block_name'].shape[0]):
                            for j in range(events['voxels']['block_name'].shape[1]):
                                for k in range(events['voxels']['block_name'].shape[2]):
                                    # Convert the element to a string and append it to 'observation'
                                    observation += str(events['voxels']['block_name'][i, j, k]) + " "
                                observation+='\n'
                            observation +='\n'
                        print(f"had to mine ahead")
                        move_to_middle(env)
                        mine_ahead_aboveground(env)
                        mined_ahead = 1
                        stuck = 0
                        direction = 0
                        retry_times = 0
                        break
                    print(f"retry times is {retry_times}")

                    while(action_stack and action_stack[-1][0]==2 and mined_ahead == 0):#action's movedir was "go right", which means that agent had no choice but go right
                        action_tuple = action_stack.pop()
                        if (action_tuple[0] == 2):
                            if not (try_leftward(env,memory,underground)):
                                print(f"had to mine ahead because can't go left")
                                move_to_middle(env)
                                mine_ahead_aboveground(env)
                                mined_ahead = 1
                                direction = 0
                                retry_times = 0
                                stuck = 0
                                break
                        
                        elif (action_tuple[0] == 0):
                            if (not try_backward(env,memory,underground)):
                                print(f"had to mine ahead because can't go back")
                                move_to_middle(env)
                                mine_ahead_aboveground(env)
                                mined_ahead = 1
                                direction = 0
                                retry_times = 0
                                stuck = 0
                                break
                            retry_times = 0
                            stuck = 0
                        # move_one_block(env,3-action_tuple[0],0,1-action_tuple[1])
                    if (not action_stack ) and (not mined_ahead):
                        print("Exception encountered, may be stuck permanently!! but i will venture a step forward")# tbd: think of some other way to let agent extricate himself
                        move_to_middle(env)
                        mine_ahead_aboveground(env)
                        direction = 0
                        flag = True
                        break
                        # return
                    elif (not mined_ahead):
                        action_tuple = action_stack.pop()
                        # print(f"action_tuple's direction is {action_tuple[0]}")
                        move_one_block(env,memory,3,0,1-action_tuple[1])
                        stuck = 0
                        if (try_rightward(env,memory,underground,0)):
                            print(f"moved rightward in new endeavor and position now is {events['location_stats']['pos']}")
                            direction = 0
                            break
                if (not action_stack):
                    print("Exception encountered, stuck permanently!!")# tbd: think of some other way to let agent extricate himself
                    # return
            if direction == 0:
                if (not try_forward(env,memory,underground)):
                    print(f"meant to go forward, rightward instead")
                    observation = ""
                    for i in range(events['voxels']['block_name'].shape[0]):
                        for j in range(events['voxels']['block_name'].shape[1]):
                            for k in range(events['voxels']['block_name'].shape[2]):
                                # Convert the element to a string and append it to 'observation'
                                observation += str(events['voxels']['block_name'][i, j, k]) + " "
                            observation+='\n'
                        observation +='\n'
                    #print(observation)
                    direction = 2
                    continue
                    # record this position in stack
                    # add another 
                else:
                    print("went forward as planned, want to continue forward")
                    direction = 0
                    continue
            if direction == 1:
                if (not try_leftward(env,memory,underground)):
                    direction = 0
                    continue
                else:
                    direction = 0
                    continue
            if direction == 2:
                if (not try_rightward(env,memory,underground,0)):
                    print(f"meant to go rightward, but can't")
                    observation = ""
                    for i in range(events['voxels']['block_name'].shape[0]):
                        for j in range(events['voxels']['block_name'].shape[1]):
                            for k in range(events['voxels']['block_name'].shape[2]):
                                # Convert the element to a string and append it to 'observation'
                                observation += str(events['voxels']['block_name'][i, j, k]) + " "
                            observation+='\n'
                        observation +='\n'
                    #print(observation)
                    direction = 0
                    continue
                else:
                    print("went rightward as planned, want to go forward now")
                    direction = 0
                    continue
        print("end of exploration")
        return False
    else:
        if(args['obj']=="log"):
            object="wood"
        elif args['obj'] == "cobblestone":
            object = "stone"
        elif args['obj'] =="diamond":
            object = "diamond ore"
        for i in range(max_try_steps):
            # create_observation(env,f"observation_{i}")
            # move_one_block(env,0,1,1)
            events = sleep(env)
            print(f"try step is {i} and dir is {direction}")
            print(f"explore step is {explore_steps} and position is {events['location_stats']['pos']}")
            
            if surrounding_voxel_detect(env, object):
                print("Found object {object}!!!yay")
                return True
            if explore_steps >= 10000:
                print("explore steps exceed limit")
                explore_steps = 0
                return False
            if args['obj'] in memory.inventory:
                return True
            #print(f"object is {object},{events['voxels']['block_name']}")
            print(f"args obj is {args['obj']},object is {object}")
            #print(f"my inventory is {memory.inventory}")
            #left
            move_one_block(env,memory,0,1,1)

# go out to top             
def go_out(env):
    events = sleep(env)
    curlevel = events['location_stats']['pos'][1]
    out_level = curlevel + 10
    go_up(out_level)
    for i in range(10):
        events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)

def go_down_to_y_level(env,goal_level,equipment = ""):
    events  = sleep(env)
    move_to_middle(env)
    inventory = events['inventory']['name'].tolist()
    try:
        cb_inventory_index = inventory.index(equipment)
    except ValueError:
        cb_inventory_index = -1 
        print(f"no equipment {equipment} found3333333333333")
    if (cb_inventory_index != -1):
        events = sleep(env)
        events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip tool
        print(f"found equipment {equipment}")

    curlevel = events['location_stats']['pos'][1]
    pre_level = curlevel
    if (curlevel > goal_level):
        events,reward,ended,addinfo = env.step([0,0,0,18,12,0,0,0]); save_rgb_for_video(events)  
        stalled_steps = 0
        for dig_try_idx in range(80):
            if curlevel <= goal_level:
                break
            print(f"present level is { events['location_stats']['pos'][1]}")
            events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
            events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
            events,reward,ended,addinfo = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events)
            events = sleep(env)
            curlevel = events['location_stats']['pos'][1]
            if (curlevel >= pre_level - 0.05):
                stalled_steps += 1
                events,reward,ended,addinfo = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                if stalled_steps >= 5:
                    print(
                        f"go_down_to_y_level stalled at {curlevel} while targeting {goal_level}; "
                        "leaving dig_down so the workflow can continue."
                    )
                    break
            else:
                stalled_steps = 0
            pre_level = curlevel
        events,reward,ended,addinfo = env.step([0,0,0,6,12,0,0,0]); save_rgb_for_video(events)  
    else:
    # events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)  
    
        #cb_inventory_index = events['inventory']['name'].tolist().index('dirt')  #################for debug, could be changed
        #events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip dirt
        return
    #cb_inventory_index = events['inventory']['name'].tolist().index('dirt')  #################for debug, could be changed
    #events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip dirt

def select_target_block(events, object_name):
    current_x = events['location_stats']['pos'][0]
    current_y = events['location_stats']['pos'][1]
    current_z = events['location_stats']['pos'][2]
    best_target = None
    best_score = None

    for x_index in range(vradius, vradius * 2 + 1):
        for y_index in range(0, vradius * 2 + 1):
            for z_index in range(0, vradius * 2 + 1):
                block_name = events['voxels']['block_name'][x_index][y_index][z_index]
                if block_name != object_name:
                    continue

                world_x = x_index - vradius + current_x
                world_y = y_index - vradius + current_y
                world_z = z_index - vradius + current_z
                below_block = events['voxels']['block_name'][x_index][y_index - 1][z_index] if y_index > 0 else "air"
                forward_distance = abs(world_x - current_x)
                side_distance = abs(world_z - current_z)
                vertical_delta = world_y - current_y

                if object_name == "wood":
                    if abs(vertical_delta) > 1:
                        continue
                    reachable_band = 0 if abs(vertical_delta) <= 1 else 1
                    trunk_like = 0 if below_block not in ("air", "water", "leaves") else 1
                    forward_bias = 0 if x_index >= vradius + 1 else 1
                    same_level_bias = 0 if abs(vertical_delta) == 0 else 1
                    side_bias = 0 if side_distance <= 1.25 else 1
                    high_side_penalty = 1 if side_distance >= 2.0 else 0
                    high_vertical_penalty = 1 if abs(vertical_delta) >= 2 else 0
                    pure_side_penalty = 1 if forward_distance < 0.5 and side_distance > 0.5 else 0
                    back_penalty = 1 if x_index <= vradius else 0
                    score = (
                        reachable_band,
                        trunk_like,
                        forward_bias,
                        same_level_bias,
                        back_penalty,
                        high_side_penalty,
                        high_vertical_penalty,
                        pure_side_penalty,
                        side_bias,
                        abs(vertical_delta),
                        side_distance,
                        forward_distance,
                        forward_distance + side_distance,
                    )
                else:
                    score = (
                        forward_distance + side_distance + abs(vertical_delta),
                        abs(vertical_delta),
                        side_distance,
                        forward_distance,
                    )

                if best_score is None or score < best_score:
                    best_score = score
                    best_target = {
                        "world_x": world_x,
                        "world_y": world_y,
                        "world_z": world_z,
                        "x_index": x_index,
                        "y_index": y_index,
                        "z_index": z_index,
                        "forward_offset": x_index - vradius,
                        "vertical_offset": y_index - vradius,
                        "side_offset": z_index - vradius,
                    }

    return best_target

    
# The function for approaching a desired object once it has already been sighted.
def approach(env,memory,object,underground):# tbd: scanning blocknames not enough if you want to approach live entity
    
    #if underground:
     #   return True
    print(f"executing approach")
    events  = sleep(env)
    events = sleep(env)
    
    if(object=="log"):
        object="wood"
    elif object == "cobblestone":
        object = "stone"
    elif object =="diamond":
        object = "diamond ore"
    print(f"object is near here")
    target_block = select_target_block(events, object)
    if target_block is None:
        print("object is not found!")
        return False

    print("found block")
    print(
        f"target offsets are forward={target_block['forward_offset']}, "
        f"side={target_block['side_offset']}, vertical={target_block['vertical_offset']}"
    )

    last_signature = None
    stagnation_count = 0
    for try_num in range(30):
        events = sleep(env)
        target_block = select_target_block(events, object)
        if target_block is None:
            print("approach lost sight of target")
            return False

        forward_offset = target_block["forward_offset"]
        side_offset = target_block["side_offset"]
        vertical_offset = target_block["vertical_offset"]

        print(
            f"approach loop {try_num + 1}: present position is {events['location_stats']['pos']}, "
            f"target offsets are forward={forward_offset}, side={side_offset}, vertical={vertical_offset}"
        )

        if interaction_ready(target_block, object):
            print(f"APPROACH ended:). present position is {events['location_stats']['pos']}")
            return True

        pos = events['location_stats']['pos']
        signature = (
            round(float(pos[0]), 2),
            round(float(pos[1]), 2),
            round(float(pos[2]), 2),
            int(forward_offset),
            int(side_offset),
            int(vertical_offset),
        )
        if signature == last_signature:
            stagnation_count += 1
        else:
            stagnation_count = 0
            last_signature = signature
        if stagnation_count >= 4:
            print("approach stagnated on same target/position signature")
            return False

        if side_offset >= 2:
            print("have to move right")
            if not try_rightward(env,memory,underground,1):
                print("stuck trying to go right in APPROACH!")
                return False
            continue

        if side_offset <= -2:
            print("have to move left")
            if not try_leftward(env,memory,underground,1):
                print("stuck trying to go left in APPROACH!")
                return False
            continue

        print("finished moving sideways")
        if forward_offset >= 2:
            if try_forward(env,memory,0,1) == False:
                print("stuck trying to go ahead in APPROACH!")
                return False
            continue

        current_y = events['location_stats']['pos'][1]
        object_y = target_block["world_y"]
        if current_y < object_y - 1:
            go_up(env, object_y - 1)
            continue
        if current_y > object_y + 1:
            go_down_to_y_level(env, object_y + 1)
            continue

        if interaction_ready(target_block, object):
            break
        if abs(side_offset) == 1:
            if side_offset > 0:
                if not try_rightward(env,memory,underground,1):
                    return False
            else:
                if not try_leftward(env,memory,underground,1):
                    return False
            continue
        if forward_offset == 1:
            if try_forward(env,memory,0,1) == False:
                return False
            continue
        break

    target_block = select_target_block(events, object)
    if target_block is not None:
        print(
            f"APPROACH ended:). present position is {events['location_stats']['pos']}, "
            f"target offsets are forward={target_block['forward_offset']}, "
            f"side={target_block['side_offset']}, vertical={target_block['vertical_offset']}"
        )
    else:
        print(f"APPROACH ended:). present position is {events['location_stats']['pos']}")
    observation = ""
    for i in range(events['voxels']['block_name'].shape[0]):
        for j in range(events['voxels']['block_name'].shape[1]):
            for k in range(events['voxels']['block_name'].shape[2]):
                # Convert the element to a string and append it to 'observation'
                observation += str(events['voxels']['block_name'][i, j, k]) + " "
            observation+='\n'
        observation +='\n'
    #print(f"observation is {observation}")
    # save_rgb_as_image(env,"approached_goal")
    newpos = []
    newpos.append(events['location_stats']['pos'][0])
    newpos.append(events['location_stats']['pos'][1])
    newpos.append(events['location_stats']['pos'][2])
    global recently_approached_object_position
    recently_approached_object_position = newpos
    
    # print("##############################################################")
    # print(events['location_stats']['pos'][0])
    # print(object_x-1)
    if np.isin(object,events['rays']['block_name']):# tbd: didn't consider entities
        indices = np.where(events['rays']['block_name'] == object)[0]
        # positions = [indices[0]]
        # pos = positions[0]
        for idx in indices:
            if events['rays']['block_distance'][idx]<3:
                return True
    if object == "wood":
        target_block = select_target_block(events, object)
        if interaction_ready(target_block, object):
            return True
    return False

# def move_forward(env):
#     _,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     _,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     _,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     _,_,_,_ = env.step([0,0,1,12,12,0,0,0]); save_rgb_for_video(events)
#     _,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     _,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)
#     _,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events)

# def attack(object, equipment):
#     right = 0
#     front = 0
#     curdir = 0# 1: 90 anticlockwise, 2: facing backwards, 3: 90 clockwise
#     if (recently_approached_object_position[0]>events['location_stats']['pos'][0]):
#         front = 1
#     elif (recently_approached_object_position[2]>events['location_stats']['pos'][2]):
#         right = 1
#     frontdistance = abs(recently_approached_object_position[0]-events['location_stats']['pos'][0])
#     rightdistance = abs(recently_approached_object_position[2]-events['location_stats']['pos'][2])
#     # if (front and right and frontdistance and rightdistance):
        
#     # elif (front and (not right) and frontdistance and rightdistance):
#     # elif (front):
#     # elif (right):
#     # elif (not right):
MC_ITEM_IDS = MC.MC_ITEM_IDS

# A function which allows the agent to do nothing for 'duration' timesteps.
def sleep(env, duration = 1):
    for i in range (duration):
        _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
        _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
        _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
        _,_,_,_ = env.step([0,0,0,12,12,0,0,0])
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0])
    return events

# The structured action for craft, it first finds level ground for a crafting table 
# if crafting table is needed, then proceeds to craft the desired tool.
def action_craft(env, item, memory,use_crafting_table,use_furnace,craft_num):
    """
    Craft item
    :env: minedojo env
    :item: item need to be crafted: string
    """
    '''
    del dirt equipment
    
    events  = sleep(env)
    equipment = "dirt"
    inventory = events['inventory']['name'].tolist()
    try:
        cb_inventory_index = inventory.index(equipment)
    except ValueError:
        cb_inventory_index = -1 
        print(f"no equipment {equipment} found")
    if (cb_inventory_index != -1):
        events = sleep(env)
        events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip tool
        print(f"found equipment {equipment}")
    '''
    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events) #get event
    recipy = MC.ALL_CRAFT_SMELT_ITEMS
    item_recipy_index = recipy.index(item)

    if (not use_crafting_table):
        if use_furnace:
            if (events['location_stats']['pos'][1]<=56):
                events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                #events = sleep(env)
        
                share_memory(memory,events)
                mine_ahead(env,memory)
            else:
                move_to_middle(env)
                events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                
                if not (events['voxels']['block_name'][vradius+1][vradius-1][vradius] not in ("air", "water") and events['voxels']['block_name'][vradius+1][vradius][vradius]=="air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air"):
                # if not (events['voxels']['block_name'][vradius+1][vradius-1][vradius]!=("air" or "water") and events['voxels']['block_name'][vradius+1][vradius][vradius]=="air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius-1]=="air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius+1]=="air" and events['voxels']['block_name'][vradius+1][vradius][vradius+1]=="air" and   events['voxels']['block_name'][vradius+1][vradius][vradius-1]=="air"):
                    explore_numb = 0
                    mine_ahead(env,memory)
                    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    while (explore_numb<20 and  (not (events['voxels']['block_name'][vradius+1][vradius-1][vradius] not in ("air", "water") and 
                                                      events['voxels']['block_name'][vradius+1][vradius][vradius]=="air" and 
                                                      events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air" and 
                                                      events['voxels']['block_name'][vradius+1][vradius+1][vradius-1]=="air" and 
                                                      events['voxels']['block_name'][vradius+1][vradius+1][vradius+1]=="air" and 
                                                      events['voxels']['block_name'][vradius+1][vradius][vradius+1]=="air" and   
                                                      events['voxels']['block_name'][vradius+1][vradius][vradius-1]=="air"))):
                        print(f"explore_numb is {explore_numb}, place not right for crafting")
                        explore_above_ground_none(env,memory,"nothing",0,3)
                        explore_numb += 1
                        events = sleep(env)
                    while not (events['voxels']['block_name'][vradius+1][vradius-1][vradius]!=("air" ) and events['voxels']['block_name'][vradius+1][vradius][vradius]=="air" and events['voxels']['block_name'][vradius+1][vradius+1][vradius]=="air" ):
                        mine_ahead(env,memory)
                        move_one_block(env,memory,3,0,0)
                        move_one_block(env,memory,3,0,0)
                        move_to_middle(env)
                        print(f"action_craft: taking a step back")
                        events = sleep(env)
                print(f"action_craft: front floor{events['voxels']['block_name'][vradius+1][vradius-1][vradius]}\n block in front of body is {events['voxels']['block_name'][vradius+1][vradius][vradius]} \n and block in front of head is {events['voxels']['block_name'][vradius+1][vradius+1][vradius]}\n begin crafting {item}")
                print(f"4444444444444")
                mine_ahead(env,memory)
                move_to_middle(env)

            events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            #events = sleep(env)
        
            share_memory(memory,events)
            cb_inventory_index = events['inventory']['name'].tolist().index('furnace')
            # cb_inventory_index = events['inventory']['name'].tolist().index('crafting table')
            
            events,_,_,_ = env.step([0,0,0,16,12,0,0,0]); save_rgb_for_video(events)
            events = sleep(env)
            events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip furnace
            events = sleep(env)
            while events['inventory']['name'].tolist()[0]=='furnace':
                events,_,_,_ = env.step([0,0,0,12,12,6,0,0]); save_rgb_for_video(events) #backward until place furnace
                events,_,_,_ = env.step([2,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            
            cb_inventory_index = events['inventory']['name'].tolist().index('coal') #equip coal
            events,_,_,_ = env.step([0,0,0,12,12,1,0,0]); save_rgb_for_video(events) #use furnace
            for i in range(craft_num):
                events,_,_,_ = env.step([0,0,0,12,12,4,item_recipy_index,0]); save_rgb_for_video(events) #craft item by craft_num
            events = sleep(env)

            cb_inventory_index = events['inventory']['name'].tolist().index('stone pickaxe')  #################for debug, could be changed
            events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip stone pickaxe

            for i in range(10):# may have to modify
                events,_,_,_ = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events) #attack 8 times to get furnace
            events,_,_,_ = env.step([0,0,0,8,12,0,0,0]); save_rgb_for_video(events) #look forward 
            events = sleep(env)
            print(events['inventory']['name'].tolist())
            print('furnace' in events['inventory']['name'].tolist())

            if 'furnace' not in events['inventory']['name'].tolist():
                for i in range(10):
                    events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events) #get furnace
                for i in range(10):
                    events,_,_,_ = env.step([2,0,0,12,12,0,0,0]); save_rgb_for_video(events) #go back
        else:
            for i in range(craft_num):
                events,_,_,_ = env.step([0,0,0,12,12,4,item_recipy_index,0]); save_rgb_for_video(events)
                events = sleep(env)
    else:
        if (events['location_stats']['pos'][1]<=56):
            print("aciton_crafting---1")
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            #events = sleep(env)
        
            share_memory(memory,events)
            print("underground crafting-table use: skip tunnel clearing and try direct crafting table interaction")
        else:
            print("aciton_crafting---4")
            move_to_middle(env)
            events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)

            print(events['voxels']['block_name'][vradius+1][vradius-1][vradius])
            print(events['voxels']['block_name'][vradius+1][vradius][vradius])
            ready_for_table = (
                events['voxels']['block_name'][vradius+1][vradius][vradius] != "water"
                and events['voxels']['block_name'][vradius+1][vradius-1][vradius] not in ("air", "water")
                and events['voxels']['block_name'][vradius+1][vradius][vradius] == "air"
                and events['voxels']['block_name'][vradius+1][vradius+1][vradius] == "air"
            )
            if not ready_for_table:
                # Keep table-placement preparation bounded; getting stuck here blocks all later tool upgrades.
                for prep_try in range(3):
                    print(f"crafting-table prep try {prep_try + 1}/3")
                    cleared = mine_ahead(env, memory, max_hits=6)
                    if not cleared:
                        print("crafting-table prep clearance failed; continuing to bounded placement recovery")
                    move_to_middle(env)
                    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
                    ready_for_table = (
                        events['voxels']['block_name'][vradius+1][vradius][vradius] != "water"
                        and events['voxels']['block_name'][vradius+1][vradius-1][vradius] not in ("air", "water")
                        and events['voxels']['block_name'][vradius+1][vradius][vradius] == "air"
                        and events['voxels']['block_name'][vradius+1][vradius+1][vradius] == "air"
                    )
                    if ready_for_table:
                        break
                    move_one_block(env,memory,3,0,0)
                    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
            print(f"action_craft: front floor{events['voxels']['block_name'][vradius+1][vradius-1][vradius]}\n block in front of body is {events['voxels']['block_name'][vradius+1][vradius][vradius]} \n and block in front of head is {events['voxels']['block_name'][vradius+1][vradius+1][vradius]}\n begin crafting {item}")
            print(f"7777777777")
            if not ready_for_table:
                # A table cannot be placed/used inside a solid tunnel. Continuing
                # here made the bootstrap loop retry UI crafting, then drift farther
                # underground without a usable pickaxe.
                print("crafting-table prep failed; aborting this craft without placement")
                name = events['inventory']['name'].tolist()
                num = events['inventory']['quantity'].tolist()
                return name, num
            else:
                mine_ahead(env,memory)
            move_to_middle(env)
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
        #events = sleep(env)
        
        share_memory(memory,events)
        print(f"{memory.inventory}")
        print('crafting table' in memory.inventory)
        
        inventory = events['inventory']['name'].tolist()
        if 'crafting table' not in inventory:
            print("crafting table is not currently in inventory; assuming it may already be placed nearby")
            name = events['inventory']['name'].tolist()
            num = events['inventory']['quantity'].tolist()
            return name, num
        cb_inventory_index = inventory.index('crafting table')
        print(f"crafting table is there")
        events,_,_,_ = env.step([0,0,0,16,12,0,0,0]); save_rgb_for_video(events)
        events = sleep(env)
        events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip crafting tabsle
        # sleep(env)
        # while events['inventory']['name'].tolist()[0]=='crafting table':
        #     events,_,_,_ = env.step([0,0,0,12,12,6,0,0]); save_rgb_for_video(events) #place crafting table
        #     events,_,_,_ = env.step([2,0,0,12,12,0,0,0]); save_rgb_for_video(events) 
        events = sleep(env)
        events,_,_,_ = env.step([0,0,0,12,12,1,0,0]); save_rgb_for_video(events) #use
        print(f"crafting .....")
        for i in range(craft_num):
            events,_,_,_ = env.step([0,0,0,12,12,4,item_recipy_index,0]); save_rgb_for_video(events) #craft item
        events = sleep(env)
        '''
        cb_inventory_index = events['inventory']['name'].tolist().index('dirt')  #################for debug, could be changed
        events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip stone pickaxe
        '''
        for i in range(5):# may have to adjust
            events,_,_,_ = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events) #attack 5 times to get crafting table
        events,_,_,_ = env.step([0,0,0,8,12,0,0,0]); save_rgb_for_video(events)
        events = sleep(env)
        
        share_memory(memory,events)
        print(f"{memory.inventory}")
        print('crafting table' in memory.inventory)

        if 'crafting table' not in memory.inventory:
            for i in range(10):
                events,_,_,_ = env.step([1,0,0,12,12,0,0,0]); save_rgb_for_video(events) #get crafting table
            for i in range(10):
                events,_,_,_ = env.step([2,0,0,12,12,0,0,0]); save_rgb_for_video(events) #go back
    #print(events['inventory']['name'].tolist())
    name = events['inventory']['name'].tolist()
    num  = events['inventory']['quantity'].tolist()


    return name, num

def go_up(env, y_level, equipment = ""):
    events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
    if equipment:
        inventory = events['inventory']['name'].tolist()
        try:
            equipment_index = inventory.index(equipment)
        except ValueError:
            equipment_index = -1
            print(f"no equipment {equipment} found for go_up")
        if equipment_index != -1:
            events,_,_,_ = env.step([0,0,0,12,12,5,0,equipment_index]); save_rgb_for_video(events)
            print(f"found equipment {equipment} for go_up")
    '''
    cb_inventory_index = events['inventory']['name'].tolist().index('dirt')  #################for debug, could be changed
    events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip cobblestone
    '''
    for i in range(6):
        turn_up(env,1)
    curlevel = events['location_stats']['pos'][1]
    stalled_steps = 0
    for go_up_try_idx in range(20):
        if curlevel >= y_level:
            break
        print(curlevel)
        pre_level = curlevel
        for i in range(10):
                events,_,_,_ = env.step([0,0,0,12,12,3,0,0]); save_rgb_for_video(events) #attack 5 times
        '''
        if  events['inventory']['name'].tolist()[0]!='dirt':
            cb_inventory_index = events['inventory']['name'].tolist().index('dirt')  #################for debug, could be changed
            events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip cobblestone
        '''
        for i in range(12):
            turn_down(env,1)
        events,_,_,_ = env.step([0,0,1,12,12,0,0,0]); save_rgb_for_video(events)
        for i in range(4):
            if  events['inventory']['name'].tolist()[0]=='dirt':
                events,_,_,_ = env.step([0,0,0,12,12,6,0,0]); save_rgb_for_video(events)
        for i in range(12):
            turn_up(env,1)
        curlevel = events['location_stats']['pos'][1]
        if curlevel <= pre_level + 0.05:
            stalled_steps += 1
            if stalled_steps >= 3:
                print(f"go_up stalled at {curlevel} while targeting {y_level}; returning to caller.")
                break
        else:
            stalled_steps = 0

    for i in range(6):
        turn_down(env,1)

# Helper function.
def turn_up(env, angle):
    events,_,_,_ = env.step([0,0,0,12-angle,12,0,0,0]); save_rgb_for_video(events)
    return events

# Helper function.
def turn_down(env, angle):
    events,_,_,_ = env.step([0,0,0,12+angle,12,0,0,0]); save_rgb_for_video(events)
    return events

# the function name explore_above_ground may be misleading, it is actually a function
# which can be used both in above-ground and underground scenarios,
# set parameter underground to 0 if above ground, set it to 1 if underground.
# once the agent has explored max_try_steps number of steps, it will stop regardless of whether object is within range.
def explore_above_ground_none(env,memory,object,underground,max_try_steps=10000):
    global explore_steps
    # events  = sleep(env)
    global stuck
    global direction
    global prev_position
    global retry_times
    global dontstop
    events = sleep(env)
    print(f"exploring once, front floor{events['voxels']['block_name'][vradius+1][vradius-1][vradius]}\n block in front of body is {events['voxels']['block_name'][vradius+1][vradius][vradius]} \n and block in front of head is {events['voxels']['block_name'][vradius+1][vradius+1][vradius]}\n ")
    print("here....")
    if(object=="log"):
        object="wood"
    elif object == "cobblestone":
        object = "stone"
    elif object =="diamond":
        object = "diamond ore"


    # # make sure you drop tool into inventory before exploring so as not to waste them
    # inventory = events['inventory']['name'].tolist()
    # cb_inventory_index = inventory.index('air')
    # events,_,_,_ = env.step([0,0,0,16,12,0,0,0]); save_rgb_for_video(events)
    # events = sleep(env)
    # events,_,_,_ = env.step([0,0,0,12,12,5,0,cb_inventory_index]); save_rgb_for_video(events) #equip crafting tabsle
    if (not underground):
        for i in range(max_try_steps):
            if i >= 2 and dontstop == 1:
                dontstop = 0
            # create_observation(env,f"observation_{i}")
            print(f"try step is {i} and dir is {direction}")
            print(f"explore step is {explore_steps} and position is {events['location_stats']['pos']}")

            # save_rgb_as_image(env,f"{i}")

            # if lidar_detect(env,object) and (i!=0 and dontstop == 0):
            # # if voxel_detect(env,object) and (i!=0 and dontstop == 0):
            #     print("Found object {object}!!!yay")
            #     return True
            
            if explore_steps >= 10000 :
                print("explore steps exceed limit")
                explore_steps = 0
                return False
            if (prev_position[0] != events['location_stats']['pos'][0]) or (prev_position[2] != events['location_stats']['pos'][2]):
                stuck = 0
            else:
                stuck += 1
            prev_position = events['location_stats']['pos']
    
            if stuck>2:
                print(f"stuck!!!")
                stuck = 0
                observation = ""
                for i in range(events['voxels']['block_name'].shape[0]):
                    for j in range(events['voxels']['block_name'].shape[1]):
                        for k in range(events['voxels']['block_name'].shape[2]):
                            # Convert the element to a string and append it to 'observation'
                            observation += str(events['voxels']['block_name'][i, j, k]) + " "
                        observation+='\n'
                    observation +='\n'
                # print(f"stuck observation:{observation}")
                mined_ahead = 0
                
                while (True):# an issue here
                    retry_times += 1
                    if (retry_times > 2):
                        observation = ""
                        for i in range(events['voxels']['block_name'].shape[0]):
                            for j in range(events['voxels']['block_name'].shape[1]):
                                for k in range(events['voxels']['block_name'].shape[2]):
                                    # Convert the element to a string and append it to 'observation'
                                    observation += str(events['voxels']['block_name'][i, j, k]) + " "
                                observation+='\n'
                            observation +='\n'
                        print(f"had to mine ahead")
                        move_to_middle(env)
                        mine_ahead_aboveground(env)
                        mined_ahead = 1
                        stuck = 0
                        direction = 0
                        retry_times = 0
                        break
                    print(f"retry times is {retry_times}")

                    while(action_stack and action_stack[-1][0]==2 and mined_ahead == 0):#action's movedir was "go right", which means that agent had no choice but go right
                        action_tuple = action_stack.pop()
                        if (action_tuple[0] == 2):
                            if not (try_leftward(env,memory,underground)):
                                print(f"had to mine ahead because can't go left")
                                move_to_middle(env)
                                mine_ahead_aboveground(env)
                                mined_ahead = 1
                                direction = 0
                                retry_times = 0
                                stuck = 0
                                break
                        
                        elif (action_tuple[0] == 0):
                            if (not try_backward(env,memory,underground)):
                                print(f"had to mine ahead because can't go back")
                                move_to_middle(env)
                                mine_ahead_aboveground(env)
                                mined_ahead = 1
                                direction = 0
                                retry_times = 0
                                stuck = 0
                                break
                            retry_times = 0
                            stuck = 0
                        # move_one_block(env,3-action_tuple[0],0,1-action_tuple[1])
                    if (not action_stack ) and (not mined_ahead):
                        print("Exception encountered, may be stuck permanently!! but i will venture a step forward")# tbd: think of some other way to let agent extricate himself
                        move_to_middle(env)
                        mine_ahead_aboveground(env)
                        direction = 0
                        return
                    elif (not mined_ahead):
                        action_tuple = action_stack.pop()
                        # print(f"action_tuple's direction is {action_tuple[0]}")
                        move_one_block(env,memory,3,0,1-action_tuple[1])
                        stuck = 0
                        if (try_rightward(env,memory,underground,0)):
                            print(f"moved rightward in new endeavor and position now is {events['location_stats']['pos']}")
                            direction = 0
                            break
                if (not action_stack):
                    print("Exception encountered, stuck permanently!!")# tbd: think of some other way to let agent extricate himself
                    return
            if direction == 0:
                if (not try_forward(env,memory,underground)):
                    print(f"meant to go forward, rightward instead")
                    observation = ""
                    for i in range(events['voxels']['block_name'].shape[0]):
                        for j in range(events['voxels']['block_name'].shape[1]):
                            for k in range(events['voxels']['block_name'].shape[2]):
                                # Convert the element to a string and append it to 'observation'
                                observation += str(events['voxels']['block_name'][i, j, k]) + " "
                            observation+='\n'
                        observation +='\n'
                    #print(observation)
                    direction = 2
                    continue
                    # record this position in stack
                    # add another 
                else:
                    print("went forward as planned, want to continue forward")
                    direction = 0
                    continue
            if direction == 1:
                if (not try_leftward(env,memory,underground)):
                    direction = 0
                    continue
                else:
                    direction = 0
                    continue
            if direction == 2:
                if (not try_rightward(env,memory,underground,0)):
                    print(f"meant to go rightward, but can't")
                    observation = ""
                    for i in range(events['voxels']['block_name'].shape[0]):
                        for j in range(events['voxels']['block_name'].shape[1]):
                            for k in range(events['voxels']['block_name'].shape[2]):
                                # Convert the element to a string and append it to 'observation'
                                observation += str(events['voxels']['block_name'][i, j, k]) + " "
                            observation+='\n'
                        observation +='\n'
                    #print(observation)
                    direction = 0
                    continue
                else:
                    print("went rightward as planned, want to go forward now")
                    direction = 0
                    continue
        print("end of exploration")
        return False
    else:
        for i in range(max_try_steps):
            # create_observation(env,f"observation_{i}")
            # move_one_block(env,0,1,1)
            print(f"try step is {i} and dir is {direction}")
            print(f"explore step is {explore_steps} and position is {events['location_stats']['pos']}")
            if surrounding_voxel_detect(env, object):
                print("Found object {object}!!!yay")
                return True
            if explore_steps >= 10000:
                print("explore steps exceed limit")
                explore_steps = 0
                return False
            print(f"object is {object}, {events['voxels']['block_name']}")
            #left
            move_one_block(env,memory,0,1,1)


def check_find(env,memory,object,underground):# tbd: scanning blocknames not enough if you want to approach live entity
    if underground:
        return True
    print(f"executing check find!")
    events  = sleep(env)
    events = sleep(env)
    object_x = events['location_stats']['pos'][0]
    object_y = events['location_stats']['pos'][1]
    object_z = events['location_stats']['pos'][2]
    x_found = 0
    object = update_find_obj_name(object)

    target_block = select_target_block(events, object)
    if target_block is not None:
        object_x = target_block["world_x"]
        object_y = target_block["world_y"]
        object_z = target_block["world_z"]
        z_index = target_block["z_index"]
        x_found = True
        print("found block")
        print(f"x coordinate is {events['location_stats']['pos'][2]}, z_index is {z_index}")
    print(f"present position is {events['location_stats']['pos'][0]},{events['location_stats']['pos'][1]},{events['location_stats']['pos'][2]}")
    # print(f"approaching, walking right. present position is {events['location_stats']['pos']}, goal position is {object_x},{object_y},{object_z}")
    print(f"goal position is {object_x},{object_y},{object_z}")
    if (not x_found):
        print(f"object is not found!")
        try_forward(env,memory,underground,1)
        return False
    else:
        return True



    
################################################################################################################################################################################################################

# # Do not modify configurations below rashly. 👇
# # If you want to adjust the lidar configuration, you would also have to modify the mine function.
# biome_string = "forest"
# # biome_string = "plains"
# # biome_string = "desert"
# seed = generate_random_string(env,)
# env = minedojo.make(
#     task_id="harvest",
#     image_size=(512, 820),
#     target_names="diamond",
#     target_quantities=100,
#     seed=3,
#     initial_mobs="sheep",
#     specified_biome = biome_string,
#     initial_mob_spawn_range_low=(-3, 1, -3),
#     initial_mob_spawn_range_high=(3, 3, 3),
#     spawn_rate=1,
#     break_speed_multiplier = 100.0,
#     spawn_range_low=(-10, -10, -10),
#     spawn_range_high=(10, 10, 10),
#     start_at_night = False,
#     world_seed = seed,
#     use_voxel = True,
#     voxel_size=dict(xmin=-vradius, ymin=-vradius, zmin=-vradius, xmax=vradius, ymax=vradius, zmax=vradius),# doesn't really matter
#     use_lidar=True,
#     # task_id="harvest_milk",
#     lidar_rays=[
#             (np.pi * pitch / 180, np.pi * yaw / 180, 10) # ALERT: lidar range is now 10
#             for pitch in np.arange(-60, 60, 5)
#             for yaw in np.arange(-60, 60, 5)
#     ]
# )



# env.reset()
# env.set_inventory([InventoryItem(slot=9, name="dirt", variant=None, quantity=60),])
# # env.set_inventory([InventoryItem(slot=9, name="dirt", variant=None, quantity=60),InventoryItem(slot=1, name="diamond", variant=None, quantity=3),InventoryItem(slot=2, name="crafting_table", variant=None, quantity=1),InventoryItem(slot=5, name="stick", variant=None, quantity=3)])
# # env.set_inventory([InventoryItem(slot="mainhand", name="log", variant=None, quantity=0),InventoryItem(slot=1, name="log", variant=None, quantity=0),])
# # env.set_inventory([InventoryItem(slot="mainhand", name="log", variant=None, quantity=0),InventoryItem(slot=1, name="log", variant=None, quantity=0),InventoryItem(slot=5, name="wooden_pickaxe", variant=None, quantity=1),InventoryItem(slot=6, name="crafting_table", variant=None, quantity=1),InventoryItem(slot=7, name="stick", variant=None, quantity=10)])
# with open ("log.txt",'w') as file2:
#     file2.write(f"This is the world {seed} \n")
# events,reward,ended,addinfo = env.step([0,0,0,12,6,0,0,0]); save_rgb_for_video(events)  # Facing north

# print(events['inventory']['name'])
# print(events['inventory']['quantity'])
# print(type(events['location_stats']['pos']))
# direction = 0

# # Do not modify the configurations above rashly. 👆


# # # action list for building wooden pickaxe
# # for i in range(4):
# #     explore_above_ground("wood",0)
# #     approach("wood",0)
# #     mine("wood","")
# #     print(f"print inventory:{events['inventory']['name']}\n Inventory quantity:{events['inventory']['quantity']}")
# #     print(f"{i}th mine finished")
# # for i in range(3):
# #     action_craft(env,"planks",0,0,1)

# # action_craft(env,"crafting_table",0,0,1)
# # action_craft(env,"stick",0,0,1)
# # action_craft(env,"wooden_pickaxe",1,0,1)
# # print(f"print inventory:{events['inventory']['name'].tolist()}\n Inventory quantity:{events['inventory']['quantity']}")
# # sleep(env,3)
# # # print(events)# make sure lidar rays cover desired object
# # print(seed)
# # env.close()

# # building iron pickaxe
# # for i in range(10):
# #     explore_above_ground("wood",0)
# #     approach("wood",0)
# #     mine("wood","")
# #     print(f"print inventory:{events['inventory']['name']}\n Inventory quantity:{events['inventory']['quantity']}")
# #     print(f"{i}th mine finished")


# # explore_above_ground("wood",0)
# # action_mine("Nan","",0,4)
# action_mine("wood","",0,4)
# print(f"print inventory:{events['inventory']['name']}")
# action_craft(env,"planks",0,0,4)
# action_craft(env,"stick",0,0,3)

# action_craft(env,"crafting_table",0,0,1)



# action_craft(env,"wooden_pickaxe",1,0,1)
# go_down_to_y_level(55,"wooden pickaxe")# y-level was 60 originally
# action_mine("stone","wooden pickaxe",1,11)
# action_craft(env,"stone_pickaxe",1,0,1)
# action_craft(env,"furnace",1,0,1)
# go_down_to_y_level(53,"stone pickaxe")

# # explore_above_ground("iron ore",1)
# action_mine("iron ore","stone pickaxe",1,3)

# action_craft(env,"iron_ingot",0,1,3)# craft iron ingots using furnace * 3

# # events = sleep(env)
# # print(f"print inventory:{events['inventory']['name']}")
# # pdb.set_trace()

# action_craft(env,"iron_pickaxe",1,0,1)

# go_down_to_y_level(14,"iron pickaxe")
# # explore_above_ground("diamond ore",1)
# action_mine("diamond ore","iron pickaxe",1,3)
# action_craft(env,"diamond_pickaxe",1,0,1)

# events = sleep(env)
# print(events['inventory']['name'])
# print(events['inventory']['quantity'])

# while(1):
#     pdb.set_trace()
#     sleep(env)

# env.close()



# # only craft with _
