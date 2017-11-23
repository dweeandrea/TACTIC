##########################################################
#
# Copyright (c) 2015, Southpaw Technology
#                     All Rights Reserved
#
# PROPRIETARY INFORMATION.  This software is proprietary to
# Southpaw Technology, and is not to be reproduced, transmitted,
# or disclosed in any way without written permission.
#
#
#

__all__ = ['Workflow', 'WorkflowException', 'BaseWorkflowNodeHandler', 'BaseProcessTrigger', 'ProcessStatusTrigger', 'CustomProcessConfig']

import tacticenv

from pyasm.common import Common, Config, jsondumps, TacticException, Container, Environment
from pyasm.command import Trigger, Command
from pyasm.search import SearchType, Search, SObject
from pyasm.biz import Pipeline, Task, Note

'''
"node" and "manual" type nodes are synonymous, but the latter 
is preferred as of 4.5
'''


PREDEFINED = [
        'pending',
        'in_progress',
        'action',
        'complete',
        'approved',
        'reject',
        'revise',
        'error',
]


class WorkflowException(Exception):
    pass



class Workflow(object):

    def init(my, startup=False):

        #workflow = Config.get_value("services", "workflow")
        #if workflow not in [True, 'true']:
        #    return

        print "Starting Workflow Engine"

        # initialize the triggers for the workflow
        event = "process|pending"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessPendingTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)

        event = "process|action"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessActionTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)


        event = "process|complete"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessCompleteTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)

        event = "process|approved"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessApproveTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)


        event = "process|reject"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessRejectTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)


        event = "process|revise"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessReviseTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)

        event = "process|error"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessErrorTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)


        event = "process|custom"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessCustomTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)



        event = "workflow|listen"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", ProcessListenTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)

        """
        class TestCmd(Command):
            def execute(my):
                Trigger.call(my, "workflow|listen")
        cmd = TestCmd()
        Command.execute_cmd(cmd)
        """






        # by default a stataus change to a trigger calls the node's trigger
        event = "change|sthpw/task|status"
        trigger = SearchType.create("sthpw/trigger")
        trigger.set_value("event", event)
        trigger.set_value("class_name", TaskStatusChangeTrigger)
        trigger.set_value("mode", "same process,same transaction")
        Trigger.append_static_trigger(trigger, startup=startup)




class TaskStatusChangeTrigger(Trigger):

    def execute(my):

        """
        key = "enable_workflow_engine"
        from prod_setting import ProdSetting
        setting = ProdSetting.get_value_by_key(key)
        if setting not in [True, 'true']:
            return
        """


        # find the node in the pipeline
        task = my.get_caller()
        sobject = task.get_parent()
        if not sobject:
            return

        pipeline = None

        process_code = task.get_value("process_code", no_exception=True)
        if process_code:
            process_sobj = Search.get_by_code("config/process", process_code)
            if process_sobj:
                pipeline_code = process_sobj.get_value("pipeline_code")
                pipeline = Pipeline.get_by_code("sthpw/pipeline", pipeline_code) 

        if not pipeline:
            pipeline = Pipeline.get_by_sobject(sobject)

        if not pipeline:
            return


        if pipeline.get_value("use_workflow", no_exception=True) in [False, "false"]:
            return



        process_name = task.get_value("process")
        status = task.get_value("status")
        if status.lower() in PREDEFINED:
            status = status.lower()

        # handle the approve case (which really means complete)
        if status == "approved":
            status = "complete"


        # The task may have a hierarchy in it.  This is denoted by a / (or .) delimiter.
        # Both are supported for now, however, it is possible people will use a "/"
        # in the process name.
        parent_pipelines = []
        parent_processes = []
        parts = None
        if process_name.find(".") != -1:
            parts = process_name.split(".")

        elif process_name.find("/") != -1:
            parts = process_name.split("/")

        if parts:
            for part in parts[:-1]:
                process_name = part
                process = pipeline.get_process(process_name)

                if not process:
                    raise Exception("Process [%s] not in pipeline" % process_name)

                # find the pipeline
                search = Search("config/process")
                search.add_filter("pipeline_code", pipeline.get_code())
                search.add_filter("process", process_name)
                process_sobj = search.get_sobject()

                parent_pipeline = pipeline
                parent_pipelines.append(pipeline)
                parent_process = process_name
                parent_processes.append(process_name)

                # find the current process and pipeline_code
                pipeline_code = process_sobj.get_value("subpipeline_code")
                pipeline = Pipeline.get_by_code(pipeline_code)

                process = pipeline.get_process(parts[-1])

                break

        else:
            process = pipeline.get_process(process_name)



        if not process:
            # we don't have enough info here
            return

        node_type = process.get_type()
        process_name = process.get_name()


        if status in PREDEFINED:
            event = "process|%s" % status
        else:
            event = "process|custom"

        output = {
            'sobject': sobject,
            'pipeline': pipeline,
            'parent_pipelines': parent_pipelines,
            'process': process_name,
            'parent_processes': parent_processes,
            'status': status,
            'internal': True
        }
        Trigger.call(task, event, output=output)




class ProcessStatusTrigger(Trigger):

    def execute(my):
        process = my.input.get("process")
        pipeline_code = my.input.get("pipeline")
        status = my.input.get("status")
        sobject = my.input.get("sobject")

        pipeline = Pipeline.get_by_code(pipeline_code)

        # related process
        trigger_sobj = my.get_trigger_sobj()
        data = trigger_sobj.get_json_value("data")
        related_process_code = data.get("process_code")
        related_type = data.get("search_type")
        related_pipeline_code = data.get("pipeline_code")

        related_pipeline = Pipeline.get_by_code(related_pipeline_code)

        related_process_sobj = Search.get_by_code("config/process", related_process_code)
        related_process = related_process_sobj.get("process")
        

        # get the related sobject
        related_sobjects = Search.eval("@SOBJECT(%s)" % related_type, sobject)

        for related_sobject in related_sobjects:

            # inputs are reversed
            kwargs = {
                'sobject': related_sobject,
                'process': related_process,
                'pipeline': related_pipeline,
                'status': status,
                'related_sobject': sobject,
                'related_pipeline': pipeline,
                'related_process': process,
            }



            event = "process|%s" % status
            Trigger.call(my, event, kwargs)




#
# Built in process triggers
#


class BaseProcessTrigger(Trigger):

    def get_handler(my, node_type):
        if node_type == "action":
            handler = WorkflowActionNodeHandler(input=my.input)
        elif node_type == "approval":
            handler = WorkflowApprovalNodeHandler(input=my.input)
        elif node_type in ["manual", "node"]:
            handler = WorkflowManualNodeHandler(input=my.input)
        elif node_type == "hierarchy":
            handler = WorkflowHierarchyNodeHandler(input=my.input)
        elif node_type == "input":
            handler = WorkflowOutputNodeHandler(input=my.input)
        elif node_type == "output":
            handler = WorkflowOutputNodeHandler(input=my.input)
        elif node_type == "condition":
            handler = WorkflowConditionNodeHandler(input=my.input)
        elif node_type == "dependency":
            handler = WorkflowDependencyNodeHandler(input=my.input)
        elif node_type == "progress":
            handler = WorkflowProgressNodeHandler(input=my.input)

        elif node_type:
            extra_options = {
                    'input': my.input
            }
            handler = CustomProcessConfig.get_process_handler(node_type, extra_options)
        return handler



    def get_full_process_name(my, process):
        if process.find("/") == -1 and my.parent_processes:
            full_process_name = "%s/%s" % ("/".join(my.parent_processes), process)
        else:
            full_process_name = process

        return full_process_name



    def set_all_tasks(my, sobject, process, status):

        # prevent for instance TaskStatusChangeTrigger setting a custom task status back to complete
        if not hasattr(my, "internal"):
            my.internal = my.input.get("internal") or False

        if my.internal:
            return

        full_process_name = my.get_full_process_name(process)

        tasks = Task.get_by_sobject(sobject, process=full_process_name)
        title = status.replace("-", " ")
        title = title.replace("_", " ")
        title = Common.get_display_title(title)
        for task in tasks:
            task.set_value("status", title)
            task.commit()
 

    def run_callback(my, pipeline, process, status):

        parts = []
        if process.find(".") != -1:
            parts = process.split(".")
        if process.find("/") != -1:
            parts = process.split("/")

        if parts:
            subpipeline = parts[0]
            process = parts[-1]




        # get the node triggers
        # TODO: make this more efficient
        search = Search("config/process")        
        search.add_filter("pipeline_code", pipeline.get_code())
        search.add_filter("process", process)
        process_sobj = search.get_sobject()

        #print "callback process: ", process, pipeline.get_code()
        if not process_sobj:
            raise TacticException('Process item [%s] has not been created.'%process)



        triggers = {}
        if process_sobj:
            triggers = process_sobj.get_json_value("workflow")
        if not triggers:
            triggers = {}

        ret_val = None

        action = triggers.get("on_%s" % status)
        js_action = triggers.get("cbjs_%s" % status)
        action_path = triggers.get("on_%s_path" % status)

        kwargs, input = my.build_trigger_input()
        if action or action_path:
            from tactic.command import PythonCmd
            if action:
                cmd = PythonCmd(code=action, input=input, **kwargs)
            else:
                cmd = PythonCmd(script_path=action_path, input=input, **kwargs)

            ret_val = cmd.execute()

        elif js_action:
            from tactic.command import JsCmd
            if action:
                cmd = JsCmd(code=action, input=input, **kwargs)
            else:
                cmd = JsCmd(script_path=script_path, input=input, **kwargs)

            ret_val = cmd.execute()
        else:
            # or call a trigger
            event = "process|%s" % status

            process_code = process_sobj.get_code()
            triggers = Trigger.call(my, event, kwargs, process=process_code)
            if triggers:
                ret_val = triggers[0].get_ret_val()



        # announce callback has been called for any listeners
        """
        search_type = pipeline.get_value("search_type")
        if search_type:
            event = "workflow|%s" % search_type
            process_code = process_sobj.get_code()
            Trigger.call(my, event, kwargs, process=process_code)

            event = "workflow|%s" % search_type
            Trigger.call(my, event, kwargs, process=process)
        """


        return ret_val



    def build_trigger_input(my):
        # create a package for the trigger

        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")
        status = my.input.get("status")
        data = my.input.get("data")



        kwargs = {
            'sobject': sobject,
            'pipeline': pipeline,
            'process': process,
            'status': status,
            'data': data
        }
        input = {
            'sobject': sobject.get_sobject_dict(),
            'pipeline': pipeline.to_string(),
            'process': process,
            'status': status,
            'inputs': [x.get_name() for x in pipeline.get_input_processes(process)],
            'outputs': [x.get_name() for x in pipeline.get_output_processes(process)],
            'data': data,
        }
        return kwargs, input



    def notify_listeners(my, sobject, process, status):

        # find all of the nodes that are listening to this status
        event = "%s|%s|%s" % (sobject.get_search_key(), process, status)
        #Trigger.call(my, event, my.input)

        # or 

        search = Search("sthpw/process")
        search.add_filter("type", "listen")
        search.add_filter("key", event)
        process_sobjs = search.get_sobjects()

        # we have all of the processes that are listening

        for process_sobj in process_sobjs:

            # for each process, we need to find the related sobjects


            # so what exactly does this do ...
            # shouldn't this use triggers?
            pipeline_code = process_sobj.get_value("pipeline_code")
            pipeline = Pipeline.get_by_code(pipeline_code)

            # find all of the related sobjects
            process_obj = pipeline.get_process(process)
            related_search_type = process_obj.get_attribute("search_type")
            related_status = process_obj.get_attribute("status")
            related_process = process_obj.get_attribute("process")
            related_scope = process_obj.get_attribute("scope")

            # get the node's triggers
            if not related_search_type:
                search = Search("config/process")        
                search.add_filter("process", my.process)
                search.add_filter("pipeline_code", pipeline.get_code())
                process_sobj = search.get_sobject()

                workflow = process_sobj.get_json_value("workflow", {})
                related_search_type = workflow.get("search_type")
                related_proces = workflow.get("proces")
                related_status = workflow.get("status")
                related_scope = workflow.get("scope")







    def check_complete_inputs(my):
        # this checks all the dependent inputs to determine whether they are complete.

        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        my.input['status'] = "complete"
        Trigger.call(sobject, "workflow|listen", my.input)


        caller_sobject = my.input.get("related_sobject")
        if not caller_sobject:
            return True


        related_pipeline = my.input.get("related_pipeline")
        related_process = my.input.get("related_process")
        related_search_type = caller_sobject.get_base_search_type()


        # find related sobjects
        search = Search(related_search_type)
        if related_pipeline:
            search.add_filter("pipeline_code", related_pipeline.get_value("code"))

        search.add_relationship_filter(sobject)
        related_sobjects = search.get_sobjects()

        #related_sobjects = sobject.get_related_sobjects(related_search_type)
        #related_sobjects = Search.eval("@SOBJECT(%s)" % related_search_type, sobject)
        if not related_sobjects:
            return True

        # get the message status from each of these
        keys = []
        for related_sobject in related_sobjects:
            # ignore the caller as we know that is complete
            if related_sobject.get_search_key() == caller_sobject.get_search_key():
                continue

            key = "%s|%s|status" % (related_sobject.get_search_key(), related_process)
            keys.append(key)

        # get the statuses
        search = Search("sthpw/message")
        search.add_filters("code", keys)
        message_sobjects = search.get_sobjects()


        complete = {}

        # find the status
        for message_sobject in message_sobjects:
            status = message_sobject.get_value("message")
            if status in ["complete"]:
                complete[message_sobject.get_code()] = True


        # some backwards compatibility to figure out if the related sobject is "complete"
        if False and len(message_sobjects) < len(keys):
            # look at the overall status
            for related_sobject in related_sobjects:
                key = "%s|%s|status" % (related_sobject.get_search_key(), related_process)
                overall_status = related_sobject.get_value("status", no_exception=True)
                if overall_status.lower() == "complete":
                    complete[key] = True

                else:
                    related_tasks = Search.eval("@SOBJECT(sthpw/task['process','%s'])" % related_process, related_sobject)
                    for related_task in related_tasks:
                        related_status = related_task.get_value("status")
                        if related_status.lower() == "complete":
                            complete[key] = True


        # the caller is implied to be complete
        key = "%s|%s|status" % (caller_sobject.get_search_key(), related_process)
        complete[key] = True
        #print "complete: ", complete

        # check if there are conditions which make it not complete
        is_complete = True
        for related_sobject in related_sobjects:
            key = "%s|%s|status" % (related_sobject.get_search_key(), related_process)
            if not complete.get(key):
                is_complete = False
                break


        return is_complete





    def log_message(my, sobject, process, status):

        # need to use API for now
        key = "%s|%s|status" % (sobject.get_search_key(), process)
        from tactic_client_lib import TacticServerStub
        server = TacticServerStub.get()
        server.log_message(key, status)




    def get_state(my):

        # NOTE: use messagings for now
        key = "%s|%s|state" % (my.sobject.get_search_key(), my.process)

        from tactic_client_lib import TacticServerStub
        server = TacticServerStub.get()

        state = server.get_message(key)
        state = jsonloads(state)

        """
        search = Search(state_type)
        search.add_filter("search_key", my.sobject.get_search_key())
        search.add_filter("process", my.process)
        state_sobj = search.get_sobject()
        state = state_sobj.get_json_value("state")
        """

        return state


    def store_state(my):

        # NOTE: use messagings for now
        key = "%s|%s|state" % (my.sobject.get_search_key(), my.process)

        from tactic_client_lib import TacticServerStub
        server = TacticServerStub.get()

        if not my.output_data:
            my.output_data = {}

        state = my.output_data.copy()
        snapshot = state.get("snapshot")
        if snapshot:
            state['snapshot'] = snapshot.get_sobject_dict()

        state = jsondumps(state)
        server.log_message(key, state)


        """
        state_type = "???"

        state_obj = SearchType.create(state_type)
        state_obj.set_value("search_key", my.sobject.get_search_key())
        state_obj.set_value("process", my.process)

        state = my.output_data
        state_sobj.set_json_value("state", state)

        state_sobj.commit()
        """






class BaseWorkflowNodeHandler(BaseProcessTrigger):

    def __init__(my, **kwargs):
        super(BaseWorkflowNodeHandler, my).__init__(**kwargs)
        my.kwargs = kwargs
        my.input = kwargs.get("input")
        my.name = kwargs.get("name")

        my.pipeline = my.input.get("pipeline")
        my.parent_pipelines = my.input.get("parent_pipelines") or []
        my.process = my.input.get("process")
        my.parent_processes = my.input.get("parent_processes") or []
        my.sobject = my.input.get("sobject")
        my.input_data = my.input.get("data")
        my.data = my.input_data
        my.internal = my.input.get("internal") or False

        if my.process.find(".") != -1:
            parts = my.process.split(".")
            my.process = parts[-1]
            my.process_parts = parts[:-1]
        else:
            my.process_parts = []


    def set_name(my, name):
        my.name = name

        

    def check_inputs(my):
        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        print "check_input: ", process

        # first check the inputs.  If there is only one input, then
        # skip this check
        input_processes = pipeline.get_input_processes(process)
        if len(input_processes) <= 1:
            return True


        # check all of the input processes to see if they are all complete
        complete = True
        for input_process in input_processes:
            key = "%s|%s|status" % (sobject.get_search_key(), input_process.get_name())
            message_sobj = Search.get_by_code("sthpw/message", key)
            if message_sobj:
                message = message_sobj.get_json_value("message")
                if message != "complete":
                    complete = False
                    break
            else:
                # look for some other means to determine if this is done
                search = Search("sthpw/task")
                search.add_parent_filter(sobject)
                search.add_filter("process", input_process.get_name())
                task = search.get_sobject()
                if task:
                    task_status = task.get("status")
                    if status.lower() != "complete":
                        complete = False
                        break


        if not complete:
            return False
        else:
            return True




    def handle_pending(my):

        if not my.check_inputs():
            return

        # simply calls action
        my.log_message(my.sobject, my.process, "pending")
        my.set_all_tasks(my.sobject, my.process, "pending")
        my.run_callback(my.pipeline, my.process, "pending")

        Trigger.call(my, "process|action", output=my.input)


    def handle_action(my):

        my.log_message(my.sobject, my.process, "in_progress")
        my.set_all_tasks(my.sobject, my.process, "in_progress")
        my.run_callback(my.pipeline, my.process, "action")

        Trigger.call(my, "process|complete", output=my.input)


    def handle_complete(my):


        # run a nodes complete trigger
        status = "complete"
        my.log_message(my.sobject, my.process, status)
        my.set_all_tasks(my.sobject, my.process, "complete")
        
        my.run_callback(my.pipeline, my.process, status)

        process_obj = my.pipeline.get_process(my.process)





        my.output_data = my.data
        # ---------------------------------------
        # build the output data
        search = Search("config/process")        
        search.add_filter("process", my.process)
        search.add_filter("pipeline_code", my.pipeline.get_code())
        process_sobj = search.get_sobject()
        if process_sobj:
            workflow = process_sobj.get_json_value("workflow", {})
        else:
            workflow = {}

        process_output = workflow.get("output")
        if process_output:
            my.output_data = process_output.copy()

            output_type = process_output.get("type")
            if output_type == "file":
                my.output_data['snapshot'] = None
                my.output_data['path'] = process_output.get("path")

            # default is snapshot
            else:
                from pyasm.biz import Snapshot

                context = process_output.get("context")
                if context:
                    contexts = context.split(",")
                    context = contexts[0]
                    snapshot = Snapshot.get_latest_by_sobject(my.sobject, context=context)

                else:
                    # else get the latest checkin from the process
                    snapshot = Snapshot.get_latest_by_sobject(my.sobject, process=process_output.get("process"))

                if snapshot:
                    my.output_data['snapshot'] = snapshot
                    my.output_data['path'] = snapshot.get_lib_path_by_type()

        my.store_state()
        # ---------------------------------------



        # call the process|pending event for all output processes
        output_processes = my.pipeline.get_output_processes(my.process)
        for output_process in output_processes:
            output_process = output_process.get_name()

            #if my.process_parts:
            #    output_process = "%s.%s" % (my.process_parts[0], output_process)

            output = {
                'pipeline': my.pipeline,
                'sobject': my.sobject,
                'parent_pipelines': my.parent_pipelines,
                'parent_processes': my.parent_processes,
                'process': output_process,
                'data': my.output_data
            }

            event = "process|pending"
            Trigger.call(my, event, output)


        # if there are no output processes then check for any hierarchy
        if not output_processes and my.parent_processes:
            print "parent_pipelines: ", my.parent_pipelines
            print "parent_processes: ", my.parent_processes
            # send a message up the hierarchy
            parent_pipelines = my.parent_pipelines[:]
            pipeline = parent_pipelines.pop()

            parent_processes = my.parent_processes[:]
            process = parent_processes.pop()

            output = {
                'sobject': my.sobject,
                'pipeline': pipeline,
                'parent_pipelines': parent_pipelines,
                'parent_processes': parent_processes,
                'process': process,
                'data': my.output_data
            }

            event = "process|complete"
            Trigger.call(my, event, output)





    def handle_reject(my):

        my.log_message(my.sobject, my.process, "reject")
        my.run_callback(my.pipeline, my.process, "reject")

        # set all tasks in the process to revise
        my.set_all_tasks(my.sobject, my.process, "reject")

        process_obj = my.pipeline.get_process(my.process)

        # send revise single to previous processes
        input_processes = my.pipeline.get_input_processes(my.process)
        for input_process in input_processes:
            input_process = input_process.get_name()

            if my.process_parts:
                input_process = "%s.%s" % (my.process_parts[0], input_process)


            error = my.input.get("error")

            input = {
                'pipeline': my.pipeline,
                'sobject': my.sobject,
                'process': input_process,
                'parent_pipelines': my.parent_pipelines,
                'parent_processes': my.parent_processes,
                'error': my.input.get("error") or "Reject from %s" % my.process,
            }

            event = "process|revise"
            Trigger.call(my, event, input)



    def handle_revise(my):

        my.log_message(my.sobject, my.process, "revise")
        my.run_callback(my.pipeline, my.process, "revise")
        # set all tasks in the process to revise
        my.set_all_tasks(my.sobject, my.process, "revise")

        process_obj = my.pipeline.get_process(my.process)

        error = my.input.get("error")


        """
        if node_type in ["condition", "action", "approval"]:

            my.set_all_tasks(sobject, process, "")

            input_processes = pipeline.get_input_processes(process)
            for input_process in input_processes:
                input_process = input_process.get_name()

                input = {
                    'pipeline': pipeline,
                    'sobject': sobject,
                    'process': input_process
                }

                event = "process|revise"
                Trigger.call(my, event, input)


        else:
            my.set_all_tasks(sobject, process, my.get_status())
        """



        # send revise single to previous processes
        input_processes = my.pipeline.get_input_processes(my.process)
        for input_process in input_processes:
            input_process = input_process.get_name()

            if my.process_parts:
                input_process = "%s.%s" % (my.process_parts[0], input_process)


            input = {
                'pipeline': my.pipeline,
                'sobject': my.sobject,
                'parent_pipelines': my.parent_pipelines,
                'parent_processes': my.parent_processes,
                'process': input_process,
                'error': my.input.get("error")
            }

            event = "process|revise"
            Trigger.call(my, event, input)



class WorkflowManualNodeHandler(BaseWorkflowNodeHandler):

    def handle_pending(my):

        if not my.check_inputs():
            return

        # simply calls action
        my.log_message(my.sobject, my.process, "pending")



        search = Search("config/process")        
        search.add_filter("process", my.process)
        search.add_filter("pipeline_code", my.pipeline.get_code())
        process_sobj = search.get_sobject()
        autocreate_task = False
        mapped_status = "pending"

        if process_sobj:
            workflow = process_sobj.get_json_value("workflow", {})
            if workflow.get("autocreate_task") in ['true', True]:
                autocreate_task = True
            
            process_obj = my.pipeline.get_process(my.process)
            if not process_obj:
                print "No process_obj [%s]" % process
                return

            # only if it's not internal. If it's true, set_all_tasks() returns anyways
            # this saves unnecessary map lookup
            if not my.internal:
                mapped_status = my.get_mapped_status(process_obj)
                
        

        # check to see if the tasks exist and if they don't then create one
        if autocreate_task:
            mapped_status = my.get_mapped_status(process_obj)

            full_process_name = my.get_full_process_name(my.process)
            tasks = Task.get_by_sobject(my.sobject, process=full_process_name)
            if not tasks:
                Task.add_initial_tasks(my.sobject, processes=[my.process], status=mapped_status)
            else:
                my.set_all_tasks(my.sobject, my.process, mapped_status)
        else:
            my.set_all_tasks(my.sobject, my.process, mapped_status)


        my.run_callback(my.pipeline, my.process, "pending")

        Trigger.call(my, "process|action", output=my.input)


    def get_mapped_status(my, process_obj):
        '''Get what status is mapped to Pending'''
        mapped_status = 'pending'

        status_pipeline_code = process_obj.get_task_pipeline()
        search = Search("config/process")        
        search.add_op_filters([("workflow", "like","%Pending%")])
        search.add_filter("pipeline_code", status_pipeline_code)
        pending_process_sobj = search.get_sobject()
        if pending_process_sobj:
            # verify
            workflow = pending_process_sobj.get_json_value("workflow", {})
            mapping = workflow.get('mapping')
            
            if mapping == 'Pending':
                mapped_status = pending_process_sobj.get_value('process')

        return mapped_status

    def handle_action(my):
        my.log_message(my.sobject, my.process, "in_progress")
        # does nothing
        pass



    def handle_complete(my):

        status = "complete"

        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        # make sure all of the tasks are complete
        tasks = Task.get_by_sobject(my.sobject, process=process)

        # Make sure all of the tasks are complete
        is_complete = True
        for task in tasks:
            #my.log_message(my.sobject, my.process, status)

            # FIXME: this is a temporary solution since it doesn't take into account
            # remapping of task statuses
            task_status = task.get_value("status")
            if task_status.lower() not in ['complete','approved']:
                is_complete = False
                break


        if not is_complete:
            return


        return super(WorkflowManualNodeHandler, my).handle_complete()


       
    def handle_reject(my):
        my.input['error'] = "Rejected from '%s'" % my.process
        return super(WorkflowManualNodeHandler, my).handle_reject()



    def handle_revise(my):

        process = my.input.get("process")
        sobject = my.input.get("sobject")

        error = my.input.get("error")
        if error:
            context = "%s/error" % process
            Note.create(sobject, error, context=context)

        my.log_message(my.sobject, my.process, "revise")
        my.run_callback(my.pipeline, my.process, "revise")
        # set all tasks in the process to revise
        my.set_all_tasks(my.sobject, my.process, "revise")

        # Manual tasks stop here
        #return super(WorkflowManualNodeHandler, my).handle_revise()



     


class WorkflowActionNodeHandler(BaseWorkflowNodeHandler):


    def handle_pending(my):

        if not my.check_inputs():
            return

        # simply calls action
        Trigger.call(my, "process|action", output=my.input)



    def handle_action(my):
        #print "action: ", my.process

        my.log_message(my.sobject, my.process, "in_progress")
        my.set_all_tasks(my.sobject, my.process, "in_progress")

        process_obj = my.pipeline.get_process(my.process)

        # get the node's triggers
        search = Search("config/process")        
        search.add_filter("process", my.process)
        search.add_filter("pipeline_code", my.pipeline.get_code())
        process_sobj = search.get_sobject()

        #process_sobj = my.pipeline.get_process_sobject(my.process)


        triggers = {}
        if process_sobj:
            triggers = process_sobj.get_json_value("workflow")
        if not triggers:
            triggers = {}

        action = triggers.get("on_action")
        cbjs_action = triggers.get("cbjs_action")
        action_path = triggers.get("on_action_path")
        kwargs, input = my.build_trigger_input()
        if action or action_path:
            from tactic.command import PythonCmd
            if action:
                cmd = PythonCmd(code=action, input=input, **kwargs)
            else:
                cmd = PythonCmd(script_path=action_path, input=input, **kwargs)

            ret_val = cmd.execute()

        elif cbjs_action:
            from tactic.command import JsCmd
            if cbjs_action:
                cmd = JsCmd(code=cbjs_action, input=input, **kwargs)
            else:
                cmd = JsCmd(script_path=script_path, input=input, **kwargs)

            ret_val = cmd.execute()
        else:
            # or call an action trigger
            triggers = Trigger.call(my, "process|action", input, process=process_sobj.get_code())
            # for now set it to true
            ret_val = True
            for trigger in triggers:
                try:
                    info = trigger.get_info()
                except Exception, e:
                    print "WARNING: trigger [%s] does not support get_info" % trigger
                    continue

                ret_val = info.get("result")
                if ret_val == None:
                    ret_val = True

                # as soon as one trigger specifies a value other than
                # true, that will take precedence
                if ret_val not in [True, 'true']:
                    break

        if ret_val in [False, 'false']:
            Trigger.call(my, "process|reject", my.input)
        elif ret_val in [True, 'true']:
            Trigger.call(my, "process|complete", my.input)
        elif ret_val in ["block", "wait"]:
            # NOTE: consider adding a "wait" message directly in the workflow
            pass
        else:
            Trigger.call(my, "process|%s" % ret_val, my.input)



class WorkflowApprovalNodeHandler(BaseWorkflowNodeHandler):

    def handle_pending(my):
        my.log_message(my.sobject, my.process, "pending")

        search = Search("config/process")        
        search.add_filter("process", my.process)
        search.add_filter("pipeline_code", my.pipeline.get_code())
        process_sobj = search.get_sobject()

        assigned = None
        if process_sobj:
            workflow = process_sobj.get_json_value("workflow", {})
            if workflow:
                assigned = workflow.get("assigned")
     

        # check to see if the tasks exist and if they don't then create one
        tasks = Task.get_by_sobject(my.sobject, process=my.process)
      
        if not tasks:
            tasks = Task.add_initial_tasks(my.sobject, processes=[my.process], assigned=assigned)
        else:
            my.set_all_tasks(my.sobject, my.process, "pending")


        Trigger.call(my, "process|action", my.input)


    def handle_action(my):
        my.log_message(my.sobject, my.process, "action")
        # does nothing
        pass


    def handle_reject(my):
        login = Environment.get_login()
        display_name = login.get("display_name")
        if not display_name:
            display_name = login.get_code()
        my.input['error'] = "Approval from '%s' Rejected" % display_name

        return super(WorkflowApprovalNodeHandler, my).handle_reject()




class WorkflowHierarchyNodeHandler(BaseWorkflowNodeHandler):

    def handle_pending(my):

        # DISABLE for now
        #if not my.check_inputs():
        #    return

        # simply calls action
        Trigger.call(my, "process|action", output=my.input)




    def handle_action(my):
        my.log_message(my.sobject, my.process, "in_progress")
        my.set_all_tasks(my.sobject, my.process, "in_progress")


        search = Search("config/process")
        search.add_filter("pipeline_code", my.pipeline.get_code())
        search.add_filter("process", my.process)
        process_sobj = search.get_sobject()
        process_code = process_sobj.get_code()



        # use child process
        subpipeline_code = process_sobj.get_value("subpipeline_code")
        if subpipeline_code:
            subpipeline = Search.get_by_code("sthpw/pipeline", subpipeline_code)
        else:
            search = Search("sthpw/pipeline")
            search.add_filter("parent_process", process_code)
            subpipeline = search.get_sobject()

        if not subpipeline:
            return


        # get the input nodes
        child_processes = subpipeline.get_processes(type=['input'])

        if not child_processes:
            child_processes = subpipeline.get_processes()

        if child_processes:
            first_process = child_processes[0]
            first_name = first_process.get_name()

            input = {
                    'pipeline': subpipeline,
                    'sobject': my.sobject,
                    'process': first_name,
                    'parent_pipelines': [my.pipeline],
                    'parent_processes': [my.process],
            }

            event = "process|pending"
            Trigger.call(my, event, input)

            full_name = "%s/%s" % (my.process, first_name)
            input = {
                    'pipeline': subpipeline,
                    'sobject': my.sobject,
                    'process': first_name,
                    'parent_pipeline': [my.pipeline],
                    'parent_processes': [my.process],
            }

            event = "process|pending"
            Trigger.call(my, event, input)










class WorkflowDependencyNodeHandler(BaseWorkflowNodeHandler):

    def handle_revise(my):
        status = "revise"
        my.log_message(my.sobject, my.process, status)
        my.set_all_tasks(my.sobject, my.process, status)
        my.run_callback(my.pipeline, my.process, status)
        return my._handle_dependency(status)

    def handle_reject(my):
        status = "reject"
        my.log_message(my.sobject, my.process, status)
        my.set_all_tasks(my.sobject, my.process, status)
        my.run_callback(my.pipeline, my.process, status)
        return my._handle_dependency(status)




    def handle_action(my):
        my.log_message(my.sobject, my.process, "in_progress")
        my.set_all_tasks(my.sobject, my.process, "in_progress")
        my.run_callback(my.pipeline, my.process, "action")
        return my._handle_dependency()


    def _handle_dependency(my, status=None):

        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        # attributes for this process
        process_obj = pipeline.get_process(process)
        related_search_type = process_obj.get_attribute("search_type")
        related_status = process_obj.get_attribute("status")
        related_process = process_obj.get_attribute("process")
        related_scope = process_obj.get_attribute("scope")
        related_wait = process_obj.get_attribute("wait")

        # get the node's triggers
        if not related_search_type:
            search = Search("config/process")        
            search.add_filter("process", process)
            search.add_filter("pipeline_code", pipeline.get_code())
            process_sobj = search.get_sobject()

            workflow = process_sobj.get_json_value("workflow", {})
            related_search_type = workflow.get("search_type")
            related_process = workflow.get("process")
            related_status = workflow.get("status")
            related_scope = workflow.get("scope")
            related_wait = workflow.get("wait")


        if not related_search_type:
            print "WARNING: no related search_type found"
            return


        if not related_process:
            print "WARNING: no related process found"
            return



        # override related_status with status passed in
        if status:
            related_status = status


        if related_search_type.startswith("@"):
            expression = related_search_type
        else:
            expression = "@SOBJECT(%s)" % related_search_type


        if related_scope == "global":
            related_sobjects = Search.eval(expression)
        else:
            related_sobjects = Search.eval(expression, sobjects=[sobject])


        for related_sobject in related_sobjects:

            # if the related_sobject is already complete, don't do anything
            key = "%s|%s|status" % (related_sobject.get_search_key(), related_process)
            message_sobj = Search.get_by_code("sthpw/message", key)
            if message_sobj:
                value = message_sobj.get_value("message")
                if related_status.lower() in ["revise", "reject"]:
                    pass
                elif value == "complete" and value not in ['revise', 'reject']:
                    continue


            # This is for unittests which don't necessarily commit changes
            related_sobject = Search.get_by_search_key(related_sobject.get_search_key())

            related_pipeline = Pipeline.get_by_sobject(related_sobject)
            if not related_process:
                # get the first one
                related_processes = related_pipeline.get_processes()
                related_process = related_processes[0]


            if related_status in ["in_progress", "In Progress"]:
                event = "process|action"
            else:
                if related_status.lower() in PREDEFINED:
                    event = "process|%s" % related_status.lower()
                else:
                    event = "process|%s" % related_status


            # inputs are reversed as it sends the message
            input = {
                'sobject': related_sobject,
                'pipeline': related_pipeline,
                'process': related_process,
                'related_sobject': sobject,
                'related_pipeline': pipeline,
                'related_process': process,
            }

            Trigger.call(my, event, input)


        if status not in ['revise','reject'] and related_wait in [False, 'false', None]:
            event = "process|complete"
            Trigger.call(my, event, my.input)





#class WorkflowProgressNodeHandler(WorkflowDependencyNodeHandler):
class WorkflowProgressNodeHandler(WorkflowManualNodeHandler):

    def handle_action(my):
    
        # does nothing
        my.log_message(my.sobject, my.process, "in_progress")

        # or starts the dependent processes
        #return my._handle_dependency()



    def handle_revise(my):

        my.log_message(my.sobject, my.process, "revise")
        my.run_callback(my.pipeline, my.process, "revise")
        # set all tasks in the process to revise
        my.set_all_tasks(my.sobject, my.process, "revise")

        process_obj = my.pipeline.get_process(my.process)

        # send revise single to previous processes
        input_processes = my.pipeline.get_input_processes(my.process)
        for input_process in input_processes:
            input_process = input_process.get_name()

            if my.process_parts:
                input_process = "%s.%s" % (my.process_parts[0], input_process)


            input = {
                'pipeline': my.pipeline,
                'sobject': my.sobject,
                'process': input_process
            }

            event = "process|revise"
            Trigger.call(my, event, input)







class WorkflowInputNodeHandler(BaseWorkflowNodeHandler):

    def handle_pending(my):
        # fast track to complete
        Trigger.call(my, "process|complete", output=my.input)


class WorkflowOutputNodeHandler(BaseWorkflowNodeHandler):

    def handle_pending(my):
        # fast track to complete
        Trigger.call(my, "process|complete", output=my.input)


    def handle_complete(my):
        my.log_message(my.sobject, my.process, "complete")

        my.run_callback(my.pipeline, my.process, "complete")


        search = Search("config/process")        
        search.add_filter("subpipeline_code", my.pipeline.get_code())
        if my.process_parts:
            search.add_filter("process", my.process_parts[0])
        supprocess_sobj = search.get_sobject()
        suppipeline_code = supprocess_sobj.get_value("pipeline_code")
        supprocess = supprocess_sobj.get_value("process")

        suppipeline = Search.get_by_code("sthpw/pipeline", suppipeline_code)
        output = {
            'pipeline': suppipeline,
            'sobject': my.sobject,
            'process': supprocess,
            'data': my.data,
        }

        event = "process|complete"
        Trigger.call(my, event, output)




class WorkflowConditionNodeHandler(BaseWorkflowNodeHandler):

    def handle_pending(my):
        # fast track to complete - no tasks
        Trigger.call(my, "process|action", output=my.input)


    def handle_action(my):
        my.log_message(my.sobject, my.process, "action")

        # get the node's triggers
        search = Search("config/process")        
        search.add_filter("process", my.process)
        process_sobj = search.get_sobject()
        triggers = {}
        if process_sobj:
            triggers = process_sobj.get_json_value("workflow")
        if not triggers:
            triggers = {}

        return my.handle_condition_node(my.sobject, my.pipeline, my.process, triggers)




    def handle_condition_node(my, sobject, pipeline, process, triggers):

        ret_val = my.run_callback(pipeline, process, "action")

        # if a None return value was given, then probably no condition exists
        # yet, so just let if flow through
        if ret_val == None:
            ret_val = True

        # run the completion trigger for this node
        Trigger.call(my, "process|complete", my.input)

        from tactic.command import PythonCmd

        if ret_val == True:
            success_cbk = triggers.get("on_success")
            if success_cbk:
                cmd = PythonCmd(code=success_cbk, sobject=sobject)
                cmd.execute()
                return
            else:
                event = "process|pending"
                attr = "success"
                direction = "output"
                processes = pipeline.get_output_processes(process, from_attr=attr)
                if not processes:
                    attr = None

        elif ret_val == False:

            fail_cbk = triggers.get("on_fail")
            if fail_cbk:
                cmd = PythonCmd(code=fail_cbk, sobject=sobject)
                cmd.execute()
                return
            else:
                event = "process|revise"

                # check to see if there is an output process
                attr = "fail"
                processes = pipeline.get_output_processes(process, from_attr=attr)
                if processes:
                    direction = "output"
                else:
                    direction = "input"
                    attr = None

        else:
            event = "process|pending"
            if isinstance(ret_val, basestring): 
                ret_val = [ret_val]

            output_processes = []
            for attr in ret_val: 
                outputs = pipeline.get_output_processes(process, from_attr=attr)
                if outputs:
                    output_processes.extend(outputs)

            # if there are no output attrs, then check the node names
            if not output_processes:
                outputs = pipeline.get_output_processes(process)
                for output in outputs:
                    if output.get_name() in ret_val:
                        output_processes.append(output)

            for output_process in output_processes:
                output_process_name = output_process.get_name()
                output = {
                    'sobject': sobject,
                    'pipeline': pipeline,
                    'process': output_process_name,
                    'data': my.data
                }
                Trigger.call(my, event, output)

            return


        # by default, go back to incoming or outcoming
        if direction == "input":
            processes = pipeline.get_input_processes(process, to_attr=attr)
        else:
            processes = pipeline.get_output_processes(process, from_attr=attr)


        for process in processes:
            process_name = process.get_name()
            output = {
                'sobject': sobject,
                'pipeline': pipeline,
                'process': process_name,
                'data': my.data,
            }
            Trigger.call(my, event, output)



    def handle_complete(my):
        # run a nodes complete trigger
        my.log_message(my.sobject, my.process, "complete")
        my.run_callback(my.pipeline, my.process, "complete")

        my.set_all_tasks(my.sobject, my.process, "complete")


###---------------------------------



class ProcessPendingTrigger(BaseProcessTrigger):

  
    def execute(my):
        # set all task to pending
        
        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        if process.find(".") != -1:
            parts = process.split(".")
            process = parts[-1]

        if process.find("/") != -1:
            parts = process.split("/")
            process = parts[-1]

        process_obj = pipeline.get_process(process)

        node_type = process_obj.get_type()

        if node_type == "action":
            handler = WorkflowActionNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "approval":
            handler = WorkflowApprovalNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type in ["manual", "node"]:
            handler = WorkflowManualNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "hierarchy":
            handler = WorkflowHierarchyNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "input":
            handler = WorkflowOutputNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "output":
            handler = WorkflowOutputNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "condition":
            handler = WorkflowConditionNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "dependency":
            handler = WorkflowDependencyNodeHandler(input=my.input)
            return handler.handle_pending()
        elif node_type == "progress":
            handler = WorkflowProgressNodeHandler(input=my.input)
            return handler.handle_pending()

        else:
            handler = my.get_handler(node_type)
            return handler.handle_pending()

        """
        else:
            process_type = Search.get_by_code("sthpw/process_type", node_type)
            #handle_class = process_type.get_value("info_handler_class")
            handle_class = process_type.get_value("node_handler_class")
            handler = Common.create_from_class_path(handle_class, my.input)
            handler.handle_pending()
        """




        # Make sure the below is completely deprecated
        assert(False)



 

class ProcessActionTrigger(BaseProcessTrigger):

    def execute(my):

        # get the pipeline
        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        if process.find(".") != -1:
            parts = process.split(".")
            process = parts[-1]
        if process.find("/") != -1:
            parts = process.split("/")
            process = parts[-1]



        process_obj = pipeline.get_process(process)
        node_type = process_obj.get_type()

        if node_type == "action":
            handler = WorkflowActionNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "approval":
            handler = WorkflowApprovalNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type in ["manual", "node"]:
            handler = WorkflowManualNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "hierarchy":
            handler = WorkflowHierarchyNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "input":
            handler = WorkflowInputNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "output":
            handler = WorkflowOutputNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "condition":
            handler = WorkflowConditionNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "dependency":
            handler = WorkflowDependencyNodeHandler(input=my.input)
            return handler.handle_action()
        elif node_type == "progress":
            handler = WorkflowProgressNodeHandler(input=my.input)
            return handler.handle_action()
        else:
            handler = my.get_handler(node_type)
            return handler.handle_action()

        # Make sure the below is completely deprecated
        assert(False)





class ProcessCompleteTrigger(BaseProcessTrigger):

    def get_status(my):
        return "complete"

    def execute(my):

        process = my.input.get("process")
        sobject = my.input.get("sobject")
        pipeline = my.input.get("pipeline")
        
        if not pipeline:
            return


        # This checks all the dependent completes to see if they are complete
        # before declaring that this node is complete
        if not my.check_complete_inputs():
            my.log_message(sobject, process, "in_progress")
            return

        if process.find(".") != -1:
            parts = process.split(".")
            process = parts[-1]
        if process.find("/") != -1:
            parts = process.split("/")
            process = parts[-1]

        
        process_obj = pipeline.get_process(process)
        if process_obj:
            node_type = process_obj.get_type()
        else:
            return

        handler = None
        if node_type == "action":
            handler = WorkflowActionNodeHandler(input=my.input)
        elif node_type == "approval":
            handler = WorkflowApprovalNodeHandler(input=my.input)
        elif node_type in ["manual", "node", "progress"]:
            handler = WorkflowManualNodeHandler(input=my.input)
        elif node_type == "hierarchy":
            handler = WorkflowHierarchyNodeHandler(input=my.input)
        elif node_type == "input":
            handler = WorkflowInputNodeHandler(input=my.input)
        elif node_type == "output":
            handler = WorkflowOutputNodeHandler(input=my.input)
        elif node_type == "condition":
            handler = WorkflowConditionNodeHandler(input=my.input)
        elif node_type == "dependency":
            handler = WorkflowDependencyNodeHandler(input=my.input)
        elif node_type == "progress":
            handler = WorkflowProgressNodeHandler(input=my.input)
        else:
            handler = my.get_handler(node_type)


        if handler:
            return handler.handle_complete()


        # Make sure the below is completely deprecated
        assert(False)




class ProcessApproveTrigger(ProcessCompleteTrigger):
    def get_status(my):
        return "approved"



class ProcessRejectTrigger(BaseProcessTrigger):

    def get_status(my):
        return "reject"

    def execute(my):

        process = my.input.get("process")
        sobject = my.input.get("sobject")
        pipeline = my.input.get("pipeline")


        # This checks all the dependent completes to see if they are complete
        # before declaring that this node is complete
        if not my.check_complete_inputs():
            my.log_message(sobject, process, "in_progress")
            return


        #reject_processes = my.input.get("reject_process")

        process_obj = pipeline.get_process(process)
        node_type = process_obj.get_type()


        if node_type == "dependency":
            handler = WorkflowDependencyNodeHandler(input=my.input)
            return handler.handle_reject()
        elif node_type == "progress":
            handler = WorkflowProgressNodeHandler(input=my.input)
            return handler.handle_reject()


        else:
            handler = my.get_handler(node_type)
            return handler.handle_reject()


        """
        my.run_callback(pipeline, process, "reject")

        my.set_all_tasks(sobject, process, my.get_status())

        input_processes = pipeline.get_input_processes(process)
        for input_process in input_processes:
            input_process = input_process.get_name()

            if reject_processes:
                if input_process not in reject_processes:
                    continue

            input = {
                'pipeline': pipeline,
                'sobject': sobject,
                'process': input_process
            }

            event = "process|revise"
            Trigger.call(my, event, input)
        """




class ProcessReviseTrigger(ProcessRejectTrigger):

    def get_status(my):
        return "revise"

    def execute(my):
        pipeline = my.input.get("pipeline")
        process = my.input.get("process")
        sobject = my.input.get("sobject")

        if process.find(".") != -1:
            parts = process.split(".")
            process = parts[-1]

        process_obj = pipeline.get_process(process)
        node_type = process_obj.get_type()

        if node_type == "dependency":
            handler = WorkflowDependencyNodeHandler(input=my.input)
            return handler.handle_revise()
        elif node_type == "progress":
            handler = WorkflowProgressNodeHandler(input=my.input)
            return handler.handle_revise()

        else:
            handler = my.get_handler(node_type)
            return handler.handle_revise()



        process = my.input.get("process")
        sobject = my.input.get("sobject")
        pipeline = my.input.get("pipeline")

        my.log_message(sobject, process, my.get_status())

        process_obj = pipeline.get_process(process)
        node_type = process_obj.get_type()

        my.run_callback(pipeline, process, "revise")

        if node_type in ["condition", "action", "approval"]:

            my.set_all_tasks(sobject, process, "")

            input_processes = pipeline.get_input_processes(process)
            for input_process in input_processes:
                input_process = input_process.get_name()

                input = {
                    'pipeline': pipeline,
                    'sobject': sobject,
                    'process': input_process
                }

                event = "process|revise"
                Trigger.call(my, event, input)


        else:
            my.set_all_tasks(sobject, process, my.get_status())




class ProcessErrorTrigger(BaseProcessTrigger):

    def execute(my):
        process = my.input.get("process")
        sobject = my.input.get("sobject")
        pipeline = my.input.get("pipeline")
 
        print "Error: Failed to process [%s] on sobject [%s]" % (process, sobject.get_search_key() )

        # TODO: send a message so that those following this sobject will be notified





class CustomProcessConfig(object):
    """
    <config>
    <youtube>
        <element name="node">
          <display class="YouTubeNodeWdg"/>
        </element>
        <element name="info">
          <display class="YouTubeProcessInfoWdg"/>
        </element>
        <element name="process">
          <display class="YouTubeNodeHandler"/>
        </element>
    </youtube>
    </config>
    """

    def get_config(cls, node_type):

        category = "workflow"

        # cache already search configs
        configs = Container.get("CustomProcessConfig:configs")
        if configs == None:
            configs = {}
            Container.put("CustomProcessConfig:configs", configs)


        config = configs.get(node_type)
        if config == None:
            from pyasm.search import WidgetDbConfig

            search = Search("config/widget_config")
            search.add_filter("category", category)
            search.add_filter("view", node_type)

            config = search.get_sobject()

            configs[node_type] = config



        return config

    get_config = classmethod(get_config)




    def get_node_handler(cls, node_type, extra_options={}):
        config = cls.get_config(node_type)
        extra_options['node_type'] = node_type
        handler = config.get_display_widget("node", extra_options)
        return handler
    get_node_handler = classmethod(get_node_handler)


    def get_info_handler(cls, node_type, extra_options={}):
        config = cls.get_config(node_type)
        extra_options['node_type'] = node_type
        handler = config.get_display_widget("info", extra_options)
        return handler
    get_info_handler = classmethod(get_info_handler)


    def get_process_handler(cls, node_type, extra_options={}):
        config = cls.get_config(node_type)
        extra_options['node_type'] = node_type
        handler = config.get_display_widget("process", extra_options)
        return handler
    get_process_handler = classmethod(get_process_handler)


    def get_delete_handler(cls, node_type, extra_options={}):
        config = cls.get_config(node_type)
        extra_options['node_type'] = node_type
        handler = config.get_display_widget("delete", extra_options)
        return handler
    get_delete_handler = classmethod(get_delete_handler)









class ProcessCustomTrigger(BaseProcessTrigger):

    def execute(my):
        process = my.input.get("process")
        sobject = my.input.get("sobject")
        pipeline = my.input.get("pipeline")

        status = my.input.get("status")
        if status.lower() in PREDEFINED:
            status = status.lower()


        my.log_message(sobject, process, status)

        # FIXME: this causes an infinite loop
        #my.set_all_tasks(sobject, process, status)

        # FIXME: not sure about this "custom"
        my.run_callback(pipeline, process, "custom")


        process_obj = pipeline.get_process(process)
        if not process_obj:
            print "No process_obj [%s]" % process
            return

        status_pipeline_code = process_obj.get_task_pipeline()
        status_pipeline = Pipeline.get_by_code(status_pipeline_code)
        if not status_pipeline:
            print "No custom status pipeline [%s]" % process
            return
        
        status_processes = status_pipeline.get_process_names()

        status_obj = status_pipeline.get_process(status)
        if not status_obj:
            print "No status [%s]" % status
            return


        direction = status_obj.get_attribute("direction")
        to_status = status_obj.get_attribute("status")
        mapping = status_obj.get_attribute("mapping")
        if not to_status and not mapping:
            search = Search("config/process")        
            search.add_filter("pipeline_code", status_pipeline.get_code())
            search.add_filter("process", status)
            process_sobj = search.get_sobject()
            if process_sobj:
                workflow = process_sobj.get_json_value("workflow", {})
                direction = workflow.get("direction")
                to_status = workflow.get("status")
                mapping = workflow.get("mapping")

        if to_status and to_status.lower() in PREDEFINED:
            to_status = to_status.lower()

        #print "direction: ", direction
        #print "to_status: ", to_status


        if mapping:
            mapping = mapping.lower()
            event = "process|%s" % mapping
            Trigger.call(my.get_caller(), event, output=my.input)
        elif to_status:

            if direction == "current":
                processes = [processes_obj]
            elif direction == "input":
                processes = pipeline.get_input_processes(process)
            else:
                processes = pipeline.get_output_processes(process)


            if to_status in PREDEFINED:
                event = "process|%s" % to_status
            else:
                event = "process|custom"

            for process in processes:
                process_name = process.get_name()
                
                output = {
                    'sobject': sobject,
                    'pipeline': pipeline,
                    'process': process_name,
                    'status': to_status,
                    #'data': my.data
                }
                Trigger.call(my, event, output)

        else:
            # Do nothing
            pass



 

class ProcessListenTrigger(BaseProcessTrigger):
    '''class for listeners in the pipeline'''

    def execute(my):

        current_process_name = my.input.get("process")
        current_pipeline = my.input.get("pipeline")
        current_process = ""
        # if it has no pipeline_code set, it should exit
        if current_pipeline:
            current_process = current_pipeline.get_process(current_process_name)
        else:
            return
        current_status = my.input.get("status")
        current_sobject = my.input.get("sobject")


        listeners = Container.get("process_listeners")
        if listeners == None:
            # build up a data structure of listeners from the pipelines
            listeners = {}
            Container.put("process_listeners", listeners)


            search_type = current_sobject.get_base_search_type()
            from pyasm.biz import Schema
            schema = Schema.get()
            related_search_types = schema.get_related_search_types(search_type)
            related_search_types.append(search_type)

            # get all of the pipelines
            search = Search("sthpw/pipeline")
            search.add_filters("search_type", related_search_types)
            listen_pipelines = search.get_sobjects()

            for listen_pipeline in listen_pipelines:
                pipeline_code = listen_pipeline.get_code()
                listen_processes = listen_pipeline.get_processes()

                pipeline_code = listen_pipeline.get_value("code")

                for listen_process in listen_processes:
                    listen_stype = listen_process.get_attribute("search_type")


                    listen_status = listen_process.get_attribute("status")
                    listen_pipeline_code = listen_process.get_attribute("pipeline_code")
                    listen_process_name = listen_process.get_attribute("process")

                    if not listen_stype:
                        # get the process sobject
                        search = Search("config/process")        
                        search.add_filter("process", listen_process.get_name())
                        search.add_filter("pipeline_code", pipeline_code)
                        process_sobj = search.get_sobject()
                        if not process_sobj:
                            continue

                        workflow = process_sobj.get_json_value("workflow", {})
                        if not workflow:
                            continue

                        listen_stype = workflow.get("search_type")
                        listen_process_name = workflow.get("process")
                        listen_pipeline_code = workflow.get("pipeline_code")
                        listen_status = workflow.get("status")

                    if not listen_stype:
                        continue

                    if not listen_status:
                        listen_status = current_status


                    if listen_pipeline_code:
                        listen_key = "%s:%s:%s:%s" % (listen_stype, listen_pipeline_code, listen_process_name, listen_status)
                    else:
                        listen_key = "%s:%s:%s" % (listen_stype, listen_process_name, listen_status)

                    items = listeners.get(listen_key)
                    if items == None:
                        items = []
                        listeners[listen_key] = items

                    items.append( {
                        "pipeline": listen_pipeline,
                        "process": listen_process,
                    } )



        # need to find any listeners for this status on this process
        search_type = current_sobject.get_base_search_type()
        pipeline_code = current_pipeline.get_value("code")

        key = "%s:%s:%s" % (search_type, current_process, current_status)
        items = listeners.get(key) or []

        key2 = "%s:%s:%s:%s" % (search_type, pipeline_code, current_process, current_status)
        items2 = listeners.get(key2)

        if items2:
            items.extend(items2)


        if not items:
            return

        for item in items:

            listen_pipeline = item.get("pipeline")
            listen_process = item.get("process")

            # these process keys are actually process objects
            input = {
                'pipeline': current_pipeline,
                'sobject': current_sobject,
                'process': current_process,
                'related_pipeline': listen_pipeline,
                'related_process': listen_process,
            }


            # send a complete message to the related pipelines
            my._handle_dependency(input, "complete")


    def _handle_dependency(my, input, status="complete"):

        pipeline = input.get("pipeline")
        process_obj = input.get("process")
        process_name = process_obj.get_name()
        sobject = input.get("sobject")

        # attributes for this process
        related_pipeline = input.get("related_pipeline")
        related_process = input.get("related_process")
        related_process_name = related_process.get_name()


        # TODO: this may need to be retrieved from workflow column
        related_scope = related_process.get_attribute("scope")
        related_wait = related_process.get_attribute("wait")


        # get the search type from the related pipeline
        related_search_type = related_pipeline.get_value("search_type")

        if not related_search_type:
            print "WARNING: no related search_type found"
            return

        if not related_process:
            print "WARNING: no related process found"
            return


        # this is currently hard coded since ProcessListenTrigger is only run 
        # when ProcessCompleteTrigger is run
        # override related_status with status passed in
        related_status = "complete"


        if related_search_type.startswith("@"):
            expression = related_search_type
        else:
            expression = "@SOBJECT(%s)" % related_search_type


        if related_scope == "global":
            related_sobjects = Search.eval(expression)
        else:
            related_sobjects = Search.eval(expression, sobjects=[sobject])

        for related_sobject in related_sobjects:
            """
            # TOBE commented out
            # if the related_sobject is already complete, don't do anything
            key = "%s|%s|status" % (related_sobject.get_search_key(), related_process)

            message_sobj = Search.get_by_code("sthpw/message", key)
            if message_sobj:
                value = message_sobj.get_value("message")
                if related_status.lower() in ["revise", "reject"]:
                    pass
                elif value == "complete" and value not in ['revise', 'reject']:
                    continue
            """

            # This is for unittests which don't necessarily commit changes
            related_sobject = Search.get_by_search_key(related_sobject.get_search_key())

            related_pipeline = Pipeline.get_by_sobject(related_sobject)
            if not related_process:
                # get the first one
                related_processes = related_pipeline.get_processes()
                related_process = related_processes[0]

            # these conditions are not fully utilized since it's always complete
            if related_status in ["in_progress", "In Progress"]:
                event = "process|action"
            else:
                if related_status.lower() in PREDEFINED:
                    event = "process|%s" % related_status.lower()
                else:
                    event = "process|%s" % related_status


            # inputs are reversed as it sends the message
            input = {
                'sobject': related_sobject,
                'pipeline': related_pipeline,
                'process': related_process_name,
                'related_sobject': sobject,
                'related_pipeline': pipeline,
                'related_process': process_name,
            }


            Trigger.call(my, event, input)

