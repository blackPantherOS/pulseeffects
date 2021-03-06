# -*- coding: utf-8 -*-

import logging

import PulseEffects.libpulse as p
from gi.repository import GLib, GObject


class PulseManager(GObject.GObject):

    __gsignals__ = {
        'sink_inputs_changed': (GObject.SIGNAL_RUN_FIRST, None,
                                ()),
        'sink_input_added': (GObject.SIGNAL_RUN_FIRST, None,
                             (object,)),
        'sink_input_changed': (GObject.SIGNAL_RUN_FIRST, None,
                               (object,)),
        'sink_input_removed': (GObject.SIGNAL_RUN_FIRST, None,
                               (int,))
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self.context_ok = False
        self.default_sink_name = ''
        self.sink_is_loaded = False
        self.sink_owner_module = -1
        self.sink_idx = -1
        self.sink_monitor_name = ''
        self.sink_inputs = []
        self.max_volume = p.PA_VOLUME_NORM

        self.log = logging.getLogger('PulseEffects')

        self.app_blacklist = ['PulseEffects', 'pulseeffects', 'gsd-media-keys',
                              'GNOME Shell', 'libcanberra', 'gnome-pomodoro']

        self.media_blacklist = ['pulsesink probe']

        # wrapping callbacks
        self.ctx_cb = p.pa_context_notify_cb_t(self.context_status)
        self.server_info_cb = p.pa_server_info_cb_t(self.server_info)
        self.default_sink_info_cb = p.pa_sink_info_cb_t(self.default_sink_info)
        self.sink_info_cb = p.pa_sink_info_cb_t(self.sink_info)
        self.sink_input_info_cb = p.pa_sink_input_info_cb_t(
            self.sink_input_info)
        self.ctx_success_cb = p.pa_context_success_cb_t(self.ctx_success)
        self.subscribe_cb = p.pa_context_subscribe_cb_t(self.subscribe)

        # creating main loop and context
        self.main_loop = p.pa_threaded_mainloop_new()
        self.main_loop_api = p.pa_threaded_mainloop_get_api(self.main_loop)

        self.ctx = p.pa_context_new(self.main_loop_api, b'PulseEffects')

        p.pa_context_set_state_callback(self.ctx, self.ctx_cb, None)

        p.pa_context_connect(self.ctx, None, 0, None)

        p.pa_threaded_mainloop_start(self.main_loop)

        # waiting context

        while self.context_ok is False:
            pass

        # getting default sink name through server info

        o = p.pa_context_get_server_info(self.ctx, self.server_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

        self.log.info('default pulseaudio sink: ' + self.default_sink_name)

        # getting default sink rate through sink info. We set
        # module-null-sink to the same rate to reduce clock drift

        o = p.pa_context_get_sink_info_by_name(self.ctx,
                                               self.default_sink_name.encode(),
                                               self.default_sink_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

        self.log.info('default pulseaudio sink audio format: ' +
                      str(self.default_sink_format) +
                      '. We will use the same format.')
        self.log.info('default pulseaudio sink sampling rate: ' +
                      str(self.default_sink_rate) +
                      ' Hz. We will use the same rate.')

        # load source sink
        self.load_sink()

        # search sink inputs
        o = p.pa_context_get_sink_input_info_list(self.ctx,
                                                  self.sink_input_info_cb,
                                                  None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

        # subscribing to pulseaudio events
        p.pa_context_set_subscribe_callback(self.ctx, self.subscribe_cb,
                                            None)

        p.pa_context_subscribe(self.ctx,
                               p.PA_SUBSCRIPTION_MASK_SINK_INPUT,
                               self.ctx_success_cb, None)

    def context_status(self, context, user_data):
        state = p.pa_context_get_state(context)

        if state == p.PA_CONTEXT_READY:
            self.context_ok = True
            self.log.info('pulseaudio context started')

        elif state == p.PA_CONTEXT_FAILED:
            self.log.critical('failed to start pulseaudio context')

        elif state == p.PA_CONTEXT_TERMINATED:
            self.log.warning('pulseaudio context terminated')

    def context_disconnect(self):
        p.pa_context_disconnect(self.ctx)

    def server_info(self, context, info, user_data):
        self.default_sink_name = info.contents.default_sink_name.decode()

        server_version = info.contents.server_version.decode()
        default_source_name = info.contents.default_source_name.decode()

        self.log.info('pulseaudio version: ' + server_version)
        self.log.info('default pulseaudio source: ' + default_source_name)

    def default_sink_info(self, context, info, eol, user_data):
        if eol == 0:
            if info:
                self.default_sink_rate = info.contents.sample_spec.rate

                sample_format = info.contents.sample_spec.format

                self.default_sink_format = self.get_sample_spec_format(
                    sample_format)

    def sink_info(self, context, info, eol, user_data):
        if eol == -1:
            self.sink_is_loaded = False
        elif eol == 0:
            if info:
                self.sink_idx = info.contents.index
                self.sink_owner_module = info.contents.owner_module

                monitor_name = info.contents.monitor_source_name.decode()
                self.sink_monitor_name = monitor_name
        elif eol == 1:
            self.sink_is_loaded = True

    def get_sample_spec_format(self, code):
        if code == p.PA_SAMPLE_U8:
            return 'u8'
        elif code == p.PA_SAMPLE_ALAW:
            return 'alaw'
        elif code == p.PA_SAMPLE_ULAW:
            return 'ulaw'
        elif code == p.PA_SAMPLE_S16LE:
            return 's16le'
        elif code == p.PA_SAMPLE_S16BE:
            return 's16be'
        elif code == p.PA_SAMPLE_FLOAT32LE:
            return 'float32le'
        elif code == p.PA_SAMPLE_FLOAT32BE:
            return 'float32be'
        elif code == p.PA_SAMPLE_S32LE:
            return 's32le'
        elif code == p.PA_SAMPLE_S32BE:
            return 's32Be'
        elif code == p.PA_SAMPLE_S24LE:
            return 's24le'
        elif code == p.PA_SAMPLE_S24BE:
            return 's24be'
        elif code == p.PA_SAMPLE_S24_32LE:
            return 's24_32le'
        elif code == p.PA_SAMPLE_S24_32BE:
            return 's24_32be'
        elif code == p.PA_SAMPLE_MAX:
            return 'pa_max'
        elif code == p.PA_SAMPLE_INVALID:
            return 'invalid'

    def sink_input_info(self, context, info, eol, user_data):
        if info:
            idx = info.contents.index
            connected_sink_idx = info.contents.sink

            proplist = info.contents.proplist

            app_name = p.pa_proplist_gets(proplist, b'application.name')
            media_name = p.pa_proplist_gets(proplist, b'media.name')
            icon_name = p.pa_proplist_gets(proplist, b'application.icon_name')

            if not app_name:
                app_name = ''
            else:
                app_name = app_name.decode()

            if not media_name:
                media_name = ''
            else:
                media_name = media_name.decode()

            if (app_name not in self.app_blacklist and
                    media_name not in self.media_blacklist):
                connected = False

                if not icon_name:
                    icon_name = 'audio-x-generic-symbolic'
                else:
                    icon_name = icon_name.decode()

                if connected_sink_idx == self.sink_idx:
                    connected = True

                volume = info.contents.volume
                audio_channels = volume.channels

                max_volume_linear = 100 * \
                    p.pa_cvolume_max(volume) / p.PA_VOLUME_NORM

                resample_method = info.contents.resample_method

                if resample_method:
                    resample_method = resample_method.decode()
                else:
                    resample_method = 'null'

                sample_spec = info.contents.sample_spec
                rate = sample_spec.rate
                sample_format = self.get_sample_spec_format(sample_spec.format)

                new_input = [idx, app_name, media_name,
                             icon_name, audio_channels, max_volume_linear,
                             rate, resample_method, sample_format, connected]

                if user_data == 1:
                    GLib.idle_add(self.emit, 'sink_input_added', new_input)
                elif user_data == 2:
                    GLib.idle_add(self.emit, 'sink_input_changed', new_input)

    def load_sink_info(self):
        sink_name = 'PulseEffects'

        o = p.pa_context_get_sink_info_by_name(self.ctx, sink_name.encode(),
                                               self.sink_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

    def load_sink(self):
        sink_name = 'PulseEffects'

        self.load_sink_info()

        if not self.sink_is_loaded:
            self.log.info('loading Pulseeffects sink...')

            args = []

            sink_properties = 'device.description=\'PulseEffects\''
            sink_properties += 'device.class=\'sound\''

            args.append('sink_name=' + sink_name)
            args.append('sink_properties=' + sink_properties)
            args.append('channels=2')
            args.append('rate=' + str(self.default_sink_rate))

            argument = ' '.join(map(str, args)).encode('ascii')

            module = b'module-null-sink'

            def module_idx(context, idx, user_data):
                self.log.info('sink owner module index: ' + str(idx))

            self.module_idx_cb = p.pa_context_index_cb_t(module_idx)

            o = p.pa_context_load_module(self.ctx, module, argument,
                                         self.module_idx_cb, None)

            while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
                pass

            p.pa_operation_unref(o)

            self.load_sink_info()

            if self.sink_is_loaded:
                self.log.info('Pulseeffects sink was successfully loaded')
                self.log.info('Pulseeffects sink index:' + str(self.sink_idx))
                self.log.info('Pulseeffects sink monitor name: ' +
                              self.sink_monitor_name +
                              '. We will process audio from this source.')
            else:
                self.log.critical('Could not load sink')

    def find_sink_inputs(self):
        p.pa_context_get_sink_input_info_list(self.ctx,
                                              self.sink_input_info_cb,
                                              1)  # 1 for new

    def move_input_to_pulseeffects_sink(self, idx):
        p.pa_context_move_sink_input_by_index(self.ctx, idx,
                                              self.sink_idx,
                                              self.ctx_success_cb, None)

    def move_input_to_default_sink(self, idx):
        p.pa_context_move_sink_input_by_name(self.ctx, idx,
                                             self.default_sink_name.encode(),
                                             self.ctx_success_cb, None)

    def set_sink_input_volume(self, idx, audio_channels, value):
        cvolume = p.pa_cvolume()
        cvolume.channels = audio_channels

        raw_value = int(p.PA_VOLUME_NORM * value / 100)

        cvolume_ptr = p.pa_cvolume_set(p.get_pointer(cvolume), audio_channels,
                                       raw_value)

        p.pa_context_set_sink_input_volume(self.ctx, idx, cvolume_ptr,
                                           self.ctx_success_cb, None)

    def subscribe(self, context, event_value, idx, user_data):
        event_type = event_value & p.PA_SUBSCRIPTION_EVENT_TYPE_MASK

        if event_type == p.PA_SUBSCRIPTION_EVENT_NEW:
            p.pa_context_get_sink_input_info(self.ctx, idx,
                                             self.sink_input_info_cb,
                                             1)  # 1 for new
        elif event_type == p.PA_SUBSCRIPTION_EVENT_CHANGE:
            p.pa_context_get_sink_input_info(self.ctx, idx,
                                             self.sink_input_info_cb,
                                             2)  # 2 for changes
        elif event_type == p.PA_SUBSCRIPTION_EVENT_REMOVE:
            GLib.idle_add(self.emit, 'sink_input_removed', idx)

    def ctx_success(self, context, success, user_data):
        if not success:
            self.log.critical('context operation failed!!')

    def unload_sink(self):
        self.load_sink_info()

        p.pa_context_unload_module(self.ctx, self.sink_owner_module,
                                   self.ctx_success_cb, None)
