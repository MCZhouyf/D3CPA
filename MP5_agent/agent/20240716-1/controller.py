from utils import *
from structured_actions import *

class Controller:
    def __init__(
        self,
        memory, 
        checker
    ):
        self.memory = memory
        self.checker = checker

    def check_and_execute_workflow(self, env, workflow_dict, task_information, underground):
        events,_,_,_ = env.step([0,0,0,12,12,0,0,0]); save_rgb_for_video(events)
       
        for step in workflow_dict['workflow']:
            #share_memory(self.memory,events)
            times = int(step['times'])
            mine_finish = False
            
            for _ in range(times):
                if mine_finish:
                    break

                for action in step['actions']:

                    print(f"action is {action['name']},and  args is {action['args']}")
                    name, args = action['name'], action['args']

                    if name == "find":
                        check_result = self.check_action_preparation("find", args,task_information,events)
                        if check_result["success"]:
                            return check_result, underground
                        
                        obj = args["obj"]
                        find_obj = update_find_obj_name(obj)
                        explore_above_ground(env=env,args=args, object=find_obj, performer=self, memory=self.memory, task_information=task_information, underground=underground)
                    
                    elif name == "move_to":
                        check_result = self.check_action_preparation("move_to",  args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground

                        obj = args["obj"]
                        approach(env=env, object=obj, underground=underground)

                    elif name == "craft":
                        check_result = self.check_action_preparation("craft", args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground
                        
                        craft_name = list(args["obj"].keys())[0].replace(" ", "_")
                        craft_num = int(list(args["obj"].values())[0])

                        craft_num = update_craft_num(craft_name, craft_num)
                        print(f"action_crafting-----")
                        inventory_name_list, inventory_num_list = action_craft(env, craft_name, args["platform"]=="crafting table",args["platform"]=="furnace",craft_num=craft_num)
                        self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))

                    elif name == "mine":
                        check_result = self.check_action_preparation("mine",  args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground

                        obj = args["obj"]
                        #print(f"mine----old_inventory_obj is {self.memory.inventory}")
                        inventory_obj = update_inventory_obj_name(obj)
                        #print(f"mine----inventory_obj is {inventory_obj}")

                        tool = "" if args["tool"] is None else args["tool"]

                        inventory_name_list, inventory_num_list = mine(env=env, target=obj, equipment=tool, underground=underground)
                        #print(f"mine----inventory_name_list is {inventory_name_list}")
                        #print(f"mine----inventory_num_list is {inventory_num_list}")

                        self.memory.update_inventory(count_inventory(inventory_name_list, inventory_num_list))
                        #print(f"mine----update_inventory is{self.memory.inventory}")
                        if inventory_obj in self.memory.inventory.keys() and int(self.memory.inventory[inventory_obj]) >= times:
                            mine_finish = True

                    elif name == "fight":
                        check_result = self.check_action_preparation("fight", args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground
                    
                    elif name == "equip":
                        check_result = self.check_action_preparation("equip",args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground


                    elif name == "dig_down":
                        check_result = self.check_action_preparation("dig_down",  args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground

                        underground = True
                        tool = "" if args["tool"] is None else args["tool"]
                        go_down_to_y_level(env,args["y_level"],equipment = tool)


                    elif name == "dig_up":
                        check_result = self.check_action_preparation("dig_up",  args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground

                        underground = False
                    
                    elif name == "apply":
                        check_result = self.check_action_preparation("apply",  args,task_information,events)
                        if not check_result["success"]:
                            return check_result, underground
        
        check_result = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
        return check_result, underground
    

    def check_action_preparation(self, action_name,  args_dict,task_information,events):
        

        if action_name == "mine" or action_name == "fight" or action_name == "dig_down" or action_name == "dig_up" or action_name == "apply":
            tool = args_dict["tool"]
            if tool:
                if tool not in self.memory.inventory or self.memory.inventory[tool] <= 0:
                    check_dict = {
                        "feedback": f"You do not have 1 {tool} as the tool to complete the '{action_name}' action.",
                        "success": False,
                        "suggestion": f"Craft 1 {tool} on a crafting table as the platform first."
                    }
                    return check_dict
            check_dict = {
                        "feedback": f"You have 1 {tool} to complete the '{action_name}' action. Therefore, continue to do this action.",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        elif action_name == "equip":
            obj = args_dict["obj"]
            if obj:
                if obj not in self.memory.inventory or self.memory.inventory[obj] <= 0:
                    check_dict = {
                        "feedback": f"You do not have 1 {obj} to complete the '{action_name}' action.",
                        "success": False,
                        "suggestion": f"Craft 1 {obj} on a crafting table as the platform first."
                    }
                    return check_dict
            check_dict = {
                        "feedback": f"You have 1 {obj} to complete the '{action_name}' action.",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        
        elif action_name == "find":
            obj = args_dict["obj"]
            if obj == "wood":
                target_object = "log"
            elif obj == "stone":
                target_object = "cobblestone"
            elif obj =="diamond ore":
                target_object = "diamond"
            else:
                target_object = obj

            old_inventory = self.memory.inventory
            #print(f"old inventory is {old_inventory}")
                
            share_memory(self.memory,events)
            new_inventory = self.memory.inventory
            print(f"my inventory is {new_inventory}")

            if target_object:
                if (target_object not in self.memory.inventory or self.memory.inventory[target_object]<= 0) and (task_information['task']not in self.memory.inventory or self.memory.inventory[task_information['task']]<= 0):
                   # print(f"false{target_object},{task_information['task']}")
                    #print(f"inventory:{inventory}")
                    check_dict = {
                        "feedback": f"",
                        "success": False,
                        "suggestion": f""
                    }
                    return check_dict
                if(target_object in old_inventory) and ((old_inventory[target_object])==(new_inventory[target_object])):
                    check_dict = {
                        "feedback": f"",
                        "success": False,
                        "suggestion": f""
                    }
                    return check_dict
            
            check_dict = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict
        
        elif action_name == "craft":
            share_memory(self.memory,events)
            print(f"Crafting my inventory is {self.memory.inventory}")
            platform = args_dict["platform"]
            if platform:
                if platform not in self.memory.inventory or self.memory.inventory[platform] <= 0:
                    check_dict = {
                        "feedback": f"You do not have {platform} to complete the '{action_name}' action.",
                        "success": False
                    }
                    if platform.lower().find("crafting") != -1:
                        check_dict["suggestion"] = f"Craft a {platform} using 4 planks. If you do not have enough planks, please craft 4 planks using 1 log first."
                    elif platform.lower().find("furnace") != -1:
                        check_dict["suggestion"] = f"Craft a {platform} using 8 cobblestone. If you do not have enough cobblestone, please mine 8 cobblestone using a wooden pickaxe as the tool, primarily found at level 55 first."
                    return check_dict
            
            materials = args_dict["materials"]

            for material, quantity in materials.items():
                
                material = update_inventory_obj_name(material)
                quantity = int(quantity)

                if material not in self.memory.inventory:
                    check_dict = {
                        "feedback": f"You do not have {material} to complete the '{action_name}' action. You need {quantity} {material} but you do not have {material} in your inventory.",
                        "success": False,
                        "suggestion": f"Mine or Craft enough {material} first."
                    }
                    return check_dict
                
                elif self.memory.inventory[material] < quantity:
                    check_dict = {
                        "feedback": f"You do not have enough {material} to complete the '{action_name}' action. You need {quantity} {material} but you only have {self.memory.inventory[material]} {material} in your inventory.",
                        "success": False,
                        "suggestion": f"Mine ot Craft enough {material} first."
                    }
                    return check_dict

            check_dict = {
                        "feedback": f"You have enough materials to complete the '{action_name}' action.",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict

        else:
            # find and move_to
            check_dict = {
                        "feedback": f"",
                        "success": True,
                        "suggestion": f""
                    }
            return check_dict