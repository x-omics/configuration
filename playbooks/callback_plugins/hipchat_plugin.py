import os
import prettytable
import hipchat
import time
from ansible import utils



class CallbackModule(object):
    """Send status updates to a HipChat channel during playbook execution.

    This plugin makes use of the following environment variables:
        HIPCHAT_TOKEN (required): HipChat API token
        HIPCHAT_ROOM  (optional): HipChat room to post in. Default: ansible
        HIPCHAT_FROM  (optional): Name to post as. Default: ansible
        HIPCHAT_NOTIFY (optional): Add notify flag to important messages ("true" or "false"). Default: true
        HIPCHAT_MSG_PREFIX (option): Optional prefix to add to all hipchat messages

    Requires:
        prettytable

    """

    def __init__(self):

        if 'HIPCHAT_TOKEN' in os.environ:
            self.start_time = time.time()
            self.task_report = []
            self.last_task = None
            self.last_task_changed = False
            self.last_task_count = 0
            self.last_task_delta = 0
            self.last_task_start = time.time()
            self.only_report_changed = True
            self.room = os.getenv('HIPCHAT_ROOM', 'ansible')
            self.from_name = os.getenv('HIPCHAT_FROM', 'ansible')
            self.allow_notify = (os.getenv('HIPCHAT_NOTIFY') != 'false')
            self.hipchat_conn = hipchat.HipChat(token=os.getenv('HIPCHAT_TOKEN'))
            self.hipchat_run_description = os.getenv('HIPCHAT_RUN_DESCRIPTION', '')
            self.printed_playbook = False
            self.playbook_name = None
            self.enabled = True
        else:
            self.enabled = False

    def _send_hipchat(self, message, room=None, from_name=None, color='', message_format='text'):

        if not room:
            room = self.room
        if not from_name:
            from_name = self.from_name
        self.hipchat_conn.message_room(room, from_name, message, color=color, message_format=message_format)

    def _flush_last_task(self):
        if self.last_task:
            delta = time.time() - self.last_task_start
            self.task_report.append(dict(
                                    changed=self.last_task_changed,
                                    count=self.last_task_count,
                                    delta="{:0>.1f}".format(self.last_task_delta),
                                    task=self.last_task))
        self.last_task_count = 0
        self.last_task_changed = False
        self.last_task = None
        self.last_task_delta = 0

    def _process_message(self, msg, msg_type='STATUS'):

        if msg_type == 'OK' and self.last_task:
            if msg.get('changed', True):
                self.last_task_changed = True
            if msg.get('delta', False):
                (hour, minute, sec) = msg['delta'].split(':')
                total = float(hour) * 1200 + float(minute) * 60 + float(sec)
                self.last_task_delta += total
            self.last_task_count += 1
        else:
            self._flush_last_task()

        if msg_type == 'TASK_START':
            self.last_task = msg
            self.last_task_start = time.time()
        else:
            # move forward the last task start time
            self.last_task_start = time.time()


    def on_any(self, *args, **kwargs):
        pass

    def runner_on_failed(self, host, res, ignore_errors=False):
        if self.enabled:
            self._process_message(res, 'FAILED')

    def runner_on_ok(self, host, res):
        if self.enabled:
            # don't send the setup results
            if res['invocation']['module_name'] != "setup":
                self._process_message(res, 'OK')


    def runner_on_error(self, host, msg):
        if self.enabled:
            self._process_message(msg, 'ERROR')

    def runner_on_skipped(self, host, item=None):
        if self.enabled:
            self._process_message(item, 'SKIPPED')

    def runner_on_unreachable(self, host, res):
        pass

    def runner_on_no_hosts(self):
        pass

    def runner_on_async_poll(self, host, res, jid, clock):
        if self.enabled:
            self._process_message(res, 'ASYNC_POLL')

    def runner_on_async_ok(self, host, res, jid):
        if self.enabled:
            self._process_message(res, 'ASYNC_OK')

    def runner_on_async_failed(self, host, res, jid):
        if self.enabled:
            self._process_message(res, 'ASYNC_FAILED')

    def playbook_on_start(self):
        pass

    def playbook_on_notify(self, host, handler):
        pass

    def playbook_on_no_hosts_matched(self):
        pass

    def playbook_on_no_hosts_remaining(self):
        pass

    def playbook_on_task_start(self, name, is_conditional):
        if self.enabled:
            self._process_message(name, 'TASK_START')


    def playbook_on_vars_prompt(self, varname, private=True, prompt=None,
                                encrypt=None, confirm=False, salt_size=None,
                                salt=None, default=None):
        pass

    def playbook_on_setup(self):
        pass

    def playbook_on_import_for_host(self, host, imported_file):
        pass

    def playbook_on_not_import_for_host(self, host, missing_file):
        pass

    def playbook_on_play_start(self, pattern):
        if self.enabled:
            """Display Playbook and play start messages"""
            self.start_time = time.time()
            self.playbook_name, _ = os.path.splitext(os.path.basename(self.play.playbook.filename))
            host_list = self.play.playbook.inventory.host_list
            inventory = os.path.basename(os.path.realpath(host_list))
            subset = self.play.playbook.inventory._subset
            msg = "<b>{description}</b>: Starting ansible run for <b><i>{play}</i></b>".format(description=self.hipchat_run_description, play=self.playbook_name)
            if self.play.playbook.only_tags and 'all' not in self.play.playbook.only_tags:
                msg = msg + " with tags <b><i>{}</i></b>".format(','.join(self.play.playbook.only_tags))
            if subset:
                msg = msg + " on hosts <b><i>{}</i></b>".format(','.join(subset))
            self._send_hipchat(msg, color='purple', message_format='html')

    def playbook_on_stats(self, stats):
        if self.enabled:
            self._flush_last_task()
            delta = time.time() - self.start_time
            self.start_time = time.time()
            """Display info about playbook statistics"""
            hosts = sorted(stats.processed.keys())
            msg = "<b>{description}</b>: Finished Ansible run for <b><i>{play}</i> in {min:02} minutes, {sec:02} seconds</b><br /><br />".format(
                description=self.hipchat_run_description,
                play=self.playbook_name,
                min=int(delta / 60),
                sec=int(delta % 60))
            task_summary = prettytable.PrettyTable(['Task', 'Time', 'Count', 'Changed'])

            for task in self.task_report:
                if not task['changed'] and self.only_report_changed:
                    continue
                task_summary.add_row([task['task'], task['delta'], str(task['count']), str(task['changed'])])

            msg += task_summary.get_html_string()
            summary_table = prettytable.PrettyTable(['Ok', 'Changed', 'Unreachable', 'Failures'])

            failures = False
            unreachable = False

            for host in hosts:
                stats = stats.summarize(host)
                if stats['failures'] > 0:
                    failures = True
                if stats['unreachable'] > 0:
                    unreachable = True
                summary_table.add_row([stats[k] for k in ['ok', 'changed', 'unreachable', 'failures']])

            msg += summary_table.get_html_string()
            self._send_hipchat(msg, message_format='html')
            if failures or unreachable:
                self._send_hipchat("{description}: !!!! IMPORTANT !!!! There were failures for this run".format(self.hipchat_run_description, color='red'))
