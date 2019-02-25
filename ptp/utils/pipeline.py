#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) IBM tkornuta, Corporation 2019
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = "Tomasz Kornuta"


import logging
import inspect

import ptp

class ConfigurationError(Exception):
    """ Error thrown when encountered a configuration issue. """
    def __init__(self, msg):
        """ Stores message """
        self.msg = msg

    def __str__(self):
        """ Prints the message """
        return repr(self.msg)


class Pipeline(object):
    """
    Class responsible for instantiating the pipeline consisting of several components.
    """


    def __init__(self):
        """
        Initializes the pipeline object.
        """
        # Initialize the logger.
        self.logger = logging.getLogger("Pipeline")

        # Set initial values of all pipeline elements.
        # Single problem.
        self.problem = None
        # Empty list of all components, sorted by their priorities.
        self.__components = {}
        # Empty list of all models - it will contain only "references" to objects stored in the components list.
        self.models = []
        # Empty list of all losses - it will contain only "references" to objects stored in the components list.
        self.losses = []
        # Empty list of all loss keys. Those keys will be used to find objects that will be roots for backpropagation of gradients.
        #self.loss_keys = []


    def create_component(self, name, params):
        """
        Method creates a single component on the basis of configuration section.
        Raises ComponentError exception when encountered issues.

        :param name: Name of the section/component.

        :param params: Parameters used to instantiate all components.
        :type params: ``utils.param_interface.ParamInterface``

        :return: tuple (component, component class).
        """

        # Check presence of type.
        if 'type' not in params:
            raise ConfigurationError("Section {} does not contain the key 'type' defining the component type".format(name))

        # Get the class type.
        c_type = params["type"]

        # Get class object.
        if c_type.find("ptp.") != -1:
            # Try to evaluate it directly.
            class_obj = eval(c_type)
        else:
            # Try to find it in the main "ptp" namespace.
            class_obj = getattr(ptp, c_type)

        # Check if class is derived (even indirectly) from Component.
        c_inherits = False
        for c in inspect.getmro(class_obj):
            if c.__name__ == ptp.Component.__name__:
                c_inherits = True
                break
        if not c_inherits:
            raise ConfigurationError("Class '{}' is not derived from the Component class".format(c_type))

        # Instantiate component.
        component = class_obj(name, params)

        return component, class_obj


    def create_problem(self, name, params, log_errors=True):
        """
        Method creates a problem on the basis of configuration section.

        :param name: Name of the section/component.

        :param params: Parameters used to instantiate the problem class.
        :type params: ``utils.param_interface.ParamInterface``

        :param log_errors: Logs the detected errors (DEFAULT: TRUE)

        :return: number of detected errors.
        """
        try: 
            # Create component.
            component, class_obj = self.create_component(name, params)

            # Check if class is derived (even indirectly) from Problem.
            p_inherits = False
            for c in inspect.getmro(class_obj):
                if c.__name__ == ptp.Problem.__name__:
                    p_inherits = True
                    break
            if not p_inherits:
                raise ConfigurationError("Class '{}' is not derived from the Problem class!".format(class_obj.__name__))            
            # Ok, set problem.
            self.problem = component
            # Return zero errors.
            return 0 # errors

        except ConfigurationError as e:
            if log_errors:
                self.logger.error(e)
            return 1 # error


    def build_pipeline(self, params, log_errors=True):
        """
        Method creating the pipeline, consisting of:
            - a list components ordered by the priority (dictionary).
            - problem (as a separate "link" to object in the list of components, instance of a class derrived from Problem class)
            - models (separate list with link to objects in components dict)
            - losses (selarate list with links to objects in components dict)

        :param params: Parameters used to instantiate all components.
        :type params: ``utils.param_interface.ParamInterface``

        :param log_errors: Logs the detected errors (DEFAULT: TRUE)

        :return: number of detected errors.
        """
        errors = 0

        # Check "skip" section.
        sections_to_skip = "skip optimizer gradient_clipping terminal_conditions seed_torch seed_numpy".split()
        if "skip" in params:
            # Expand.
            sections_to_skip = [*sections_to_skip, *params["skip"].split(",")]

        for c_key, c_params in params.items():
            # The section "key" will be used as "component" name.
            try:
                # Skip "special" sections.
                if c_key in sections_to_skip:
                    self.logger.info("Skipping section '{}'".format(c_key))
                    continue
        
                # Create component.
                component, class_obj = self.create_component(c_key, c_params)

                # Check if class is derived (even indirectly) from Problem.
                for c in inspect.getmro(class_obj):
                    if c.__name__ == ptp.Problem.__name__:
                        raise ConfigurationError("Object '{}' cannot be instantiated as part of pipeline, \
                            as its class type '{}' is derived from Problem class!".format(c_key, class_obj.__name__))

                # Check presence of priority.
                if 'priority' not in c_params:
                    raise ConfigurationError("Section '{}' does not contain the key 'priority' defining the pipeline order".format(c_key))

                # Get the priority.
                try:
                    c_priority = float(c_params["priority"])
                except ValueError:
                    raise ConfigurationError("Priority '{}' in section '{}' is not a floating point number".format(c_params["priority"], c_key))

                # Check uniqueness of the priority.
                if c_priority in self.__components.keys():
                    raise ConfigurationError("Found more than one component with the same priority ('{}')".format(c_priority))

                # Add it to dict.
                self.__components[c_priority] = component

                # Check if class is derived (even indirectly) from Model.
                m_inherits = False
                for c in inspect.getmro(class_obj):
                    if c.__name__ == ptp.Model.__name__:
                        m_inherits = True
                        break
                if m_inherits:
                    # Add to list.
                    self.models.append(component)

                # Check if class is derived (even indirectly) from Loss.
                l_inherits = False
                for c in inspect.getmro(class_obj):
                    if c.__name__ == ptp.Loss.__name__:
                        l_inherits = True
                        break
                if l_inherits:
                    # Add to list.
                    self.losses.append(component)
            except ConfigurationError as e:
                if log_errors:
                    self.logger.error(e)
                errors += 1
                continue
                # end try/else
            # end for
        # List of priorities.
        self.__priorities=sorted(self.__components.keys())        

        # Return detected errors.
        return errors


    def __getitem__(self, number):
        """
        Returns the component, using the enumeration resulting from priorities.

        :param number: Number of the component in the pipeline.
        :type key: str

        :return: object of type :py:class:`Component`.

        """
        return self.__components[self.__priorities[number]]


    def __len__(self):
        """
        Returns the number of objects in the pipeline (all components + 1 for problem)
        :return: Length of the :py:class:`Pipeline`.

        """
        length = len(self.__priorities) 
        if self.problem is not None:
            length += 1
        return length

    def summarize(self):
        """
        Summarizes the pipeline by showing all its components (including problem).

        :return: Summary as a str.

        """
        # add name of the current module
        summary_str = '\n' + '='*80 + '\n'
        summary_str += 'Pipeline\n'
        summary_str += '  + Component name (type) [priority]\n'
        summary_str += '      Inputs:\n' 
        summary_str += '        key: dims, types, description\n'
        summary_str += '      Outputs:\n' 
        summary_str += '        key: dims, types, description\n'
        summary_str += '=' * 80 + '\n'

        # Print problem.
        if self.problem is None:
            summary_str += "  + Problem (None) [-1]:\n"
        else:
            summary_str += "  + {} ({}) [-1]\n".format(self.problem.name, type(self.problem).__name__)
            # Get outputs.
            summary_str += '      Outputs:\n' 
            for key,value in self.problem.output_data_definitions().items():
                summary_str += '        {}: {}, {}, {}\n'.format(key, value.dimensions, value.types, value. description)

        for prio in self.__priorities:
            # Get component
            comp = self.__components[prio]
            summary_str += "  + {} {} [{}] \n".format(comp.name, type(comp).__name__, prio)
            # Get inputs
            summary_str += '      Inputs:\n' 
            for key,value in comp.input_data_definitions().items():
                summary_str += '        {}: {}, {}, {}\n'.format(key, value.dimensions, value.types, value. description)
            # Get outputs.
            summary_str += '      Outputs:\n' 
            for key,value in comp.output_data_definitions().items():
                summary_str += '        {}: {}, {}, {}\n'.format(key, value.dimensions, value.types, value. description)
        summary_str += '=' * 80 + '\n'

        return summary_str

    def handshake(self, log=True):
        """
        Performs handshaking of inputs and outputs definitions of all components in the pipeline.

        :param log: Logs the detected errors and info (DEFAULT: TRUE)

        :return: Number of detected errors.
        """
        errors = 0
        # Get initial definitions from problem.
        all_definitions = self.problem.output_data_definitions()
        #print(all_definitions)

        for prio in self.__priorities:
            # Get component
            comp = self.__components[prio]
            # Handshake inputs and outputs.
            errors += comp.handshake_input_definitions(all_definitions, log)
            errors += comp.export_output_definitions(all_definitions, log)

        # Log final definition.
        if errors == 0 and log:
            self.logger.info("Handshake successfull")
            def_str = "Final definition of DataDict used in pipeline:"
            def_str += '\n' + '='*80 + '\n'
            def_str += '{}'.format(all_definitions)
            def_str += '\n' + '='*80 + '\n'
            self.logger.info(def_str)

        return errors

    def __call__(self, data_dict):
        """
        Method responsible for processing the data dict, using all components in the components queue.

        :param data_dict: :py:class:`ptp.utils.DataDict` object containing both input data to be processed and that will be extended by the results.

        """

        for prio in self.__priorities:
            # Get component
            comp = self.__components[prio]
            # Forward step.
            comp(data_dict)

