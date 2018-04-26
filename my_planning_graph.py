from aimacode.planning import Action
from aimacode.search import Problem
from aimacode.utils import expr, Expr
from lp_utils import decode_state


class PgNode():
    """Base class for planning graph nodes.

    includes instance sets common to both types of nodes used in a planning graph
    parents: the set of nodes in the previous level
    children: the set of nodes in the subsequent level
    mutex: the set of sibling nodes that are mutually exclusive with this node
    """

    def __init__(self):
        self.parents = set()
        self.children = set()
        self.mutex = set()

    def is_mutex(self, other) -> bool:
        """Boolean test for mutual exclusion

        :param other: PgNode
            the other node to compare with
        :return: bool
            True if this node and the other are marked mutually exclusive (mutex)
        """
        if other in self.mutex:
            return True
        return False

    def show(self):
        """helper print for debugging shows counts of parents, children, siblings

        :return:
            print only
        """
        print("{} parents".format(len(self.parents)))
        print("{} children".format(len(self.children)))
        print("{} mutex".format(len(self.mutex)))


class PgNode_s(PgNode):
    """A planning graph node representing a state (literal fluent) from a
    planning problem.

    Args:
    ----------
    symbol : Expr
        A literal expression from a planning problem domain.

    is_pos : bool
        Boolean flag indicating whether the literal expression is positive or
        negative.
    """

    def __init__(self, symbol: Expr, is_pos: bool):
        """S-level Planning Graph node constructor

        :param symbol: expr
        :param is_pos: bool
        Instance variables inherited from PgNode:
            parents: set of nodes connected to this node in previous A level; initially empty
            children: set of nodes connected to this node in next A level; initially empty
            mutex: set of sibling S-nodes that this node has mutual exclusion with; initially empty
        """
        PgNode.__init__(self)
        self.symbol = symbol
        self.is_pos = is_pos
        self.__hash = None

    def show(self):
        """helper print for debugging shows literal plus counts of parents,
        children, siblings

        :return:
            print only
        """
        if self.is_pos:
            print("\n*** {}".format(self.symbol))
        else:
            print("\n*** ~{}".format(self.symbol))
        PgNode.show(self)

    def __eq__(self, other):
        """equality test for nodes - compares only the literal for equality

        :param other: PgNode_s
        :return: bool
        """
        return (isinstance(other, self.__class__) and
                self.is_pos == other.is_pos and
                self.symbol == other.symbol)

    def __hash__(self):
        self.__hash = self.__hash or hash(self.symbol) ^ hash(self.is_pos)
        return self.__hash


class PgNode_a(PgNode):
    """A-type (action) Planning Graph node - inherited from PgNode """


    def __init__(self, action: Action):
        """A-level Planning Graph node constructor

        :param action: Action
            a ground action, i.e. this action cannot contain any variables
        Instance variables calculated:
            An A-level will always have an S-level as its parent and an S-level as its child.
            The preconditions and effects will become the parents and children of the A-level node
            However, when this node is created, it is not yet connected to the graph
            prenodes: set of *possible* parent S-nodes
            effnodes: set of *possible* child S-nodes
            is_persistent: bool   True if this is a persistence action, i.e. a no-op action
        Instance variables inherited from PgNode:
            parents: set of nodes connected to this node in previous S level; initially empty
            children: set of nodes connected to this node in next S level; initially empty
            mutex: set of sibling A-nodes that this node has mutual exclusion with; initially empty
        """
        PgNode.__init__(self)
        self.action = action
        self.prenodes = self.precond_s_nodes()
        self.effnodes = self.effect_s_nodes()
        self.is_persistent = self.prenodes == self.effnodes
        self.__hash = None

    def show(self):
        """helper print for debugging shows action plus counts of parents, children, siblings

        :return:
            print only
        """
        print("\n*** {!s}".format(self.action))
        PgNode.show(self)

    def precond_s_nodes(self):
        """precondition literals as S-nodes (represents possible parents for this node).
        It is computationally expensive to call this function; it is only called by the
        class constructor to populate the `prenodes` attribute.

        :return: set of PgNode_s
        """
        nodes = set()
        for p in self.action.precond_pos:
            nodes.add(PgNode_s(p, True))
        for p in self.action.precond_neg:
            nodes.add(PgNode_s(p, False))
        return nodes

    def effect_s_nodes(self):
        """effect literals as S-nodes (represents possible children for this node).
        It is computationally expensive to call this function; it is only called by the
        class constructor to populate the `effnodes` attribute.

        :return: set of PgNode_s
        """
        nodes = set()
        for e in self.action.effect_add:
            nodes.add(PgNode_s(e, True))
        for e in self.action.effect_rem:
            nodes.add(PgNode_s(e, False))
        return nodes

    def __eq__(self, other):
        """equality test for nodes - compares only the action name for equality

        :param other: PgNode_a
        :return: bool
        """
        return (isinstance(other, self.__class__) and
                self.is_persistent == other.is_persistent and
                self.action.name == other.action.name and
                self.action.args == other.action.args)

    def __hash__(self):
        self.__hash = self.__hash or hash(self.action.name) ^ hash(self.action.args)
        return self.__hash


def mutexify(node1: PgNode, node2: PgNode):
    """ adds sibling nodes to each other's mutual exclusion (mutex) set. These should be sibling nodes!

    :param node1: PgNode (or inherited PgNode_a, PgNode_s types)
    :param node2: PgNode (or inherited PgNode_a, PgNode_s types)
    :return:
        node mutex sets modified
    """
    if type(node1) != type(node2):
        raise TypeError('Attempted to mutex two nodes of different types')
    node1.mutex.add(node2)
    node2.mutex.add(node1)


class PlanningGraph():
    """
    A planning graph as described in chapter 10 of the AIMA text. The planning
    graph can be used to reason about
    """

    def __init__(self, problem: Problem, state: str, serial_planning=True):
        """
        :param problem: PlanningProblem (or subclass such as AirCargoProblem or HaveCakeProblem)
        :param state: str (will be in form TFTTFF... representing fluent states)
        :param serial_planning: bool (whether or not to assume that only one action can occur at a time)
        Instance variable calculated:
            fs: FluentState
                the state represented as positive and negative fluent literal lists
            all_actions: list of the PlanningProblem valid ground actions combined with calculated no-op actions
            s_levels: list of sets of PgNode_s, where each set in the list represents an S-level in the planning graph
            a_levels: list of sets of PgNode_a, where each set in the list represents an A-level in the planning graph
        """
        self.problem = problem
        self.fs = decode_state(state, problem.state_map)
        self.serial = serial_planning
        self.all_actions = self.problem.actions_list + self.noop_actions(self.problem.state_map)
        self.s_levels = []
        self.a_levels = []
        self.create_graph()

    def noop_actions(self, literal_list):
        """create persistent action for each possible fluent

        "No-Op" actions are virtual actions (i.e., actions that only exist in
        the planning graph, not in the planning problem domain) that operate
        on each fluent (literal expression) from the problem domain. No op
        actions "pass through" the literal expressions from one level of the
        planning graph to the next.

        The no-op action list requires both a positive and a negative action
        for each literal expression. Positive no-op actions require the literal
        as a positive precondition and add the literal expression as an effect
        in the output, and negative no-op actions require the literal as a
        negative precondition and remove the literal expression as an effect in
        the output.

        This function should only be called by the class constructor.

        :param literal_list:
        :return: list of Action
        """
        action_list = []
        for fluent in literal_list:
            act1 = Action(expr("Noop_pos({})".format(fluent)), ([fluent], []), ([fluent], []))
            action_list.append(act1)
            act2 = Action(expr("Noop_neg({})".format(fluent)), ([], [fluent]), ([], [fluent]))
            action_list.append(act2)
        return action_list

    def create_graph(self):
        """ build a Planning Graph as described in Russell-Norvig 3rd Ed 10.3 or 2nd Ed 11.4

        The S0 initial level has been implemented for you.  It has no parents and includes all of
        the literal fluents that are part of the initial state passed to the constructor.  At the start
        of a problem planning search, this will be the same as the initial state of the problem.  However,
        the planning graph can be built from any state in the Planning Problem

        This function should only be called by the class constructor.

        :return:
            builds the graph by filling s_levels[] and a_levels[] lists with node sets for each level
        """
        # the graph should only be built during class construction
        if (len(self.s_levels) != 0) or (len(self.a_levels) != 0):
            raise Exception(
                'Planning Graph already created; construct a new planning graph for each new state in the planning sequence')

        # initialize S0 to literals in initial state provided.
        leveled = False
        level = 0
        self.s_levels.append(set())  # S0 set of s_nodes - empty to start
        # for each fluent in the initial state, add the correct literal PgNode_s
        for literal in self.fs.pos:
            # print("literal",literal)
            # input('')
            self.s_levels[level].add(PgNode_s(literal, True))
        for literal in self.fs.neg:
            self.s_levels[level].add(PgNode_s(literal, False))
        # no mutexes at the first level

        # continue to build the graph alternating A, S levels until last two S levels contain the same literals,
        # i.e. until it is "leveled"
        while not leveled:
            self.add_action_level(level)
            self.update_a_mutex(self.a_levels[level])

            level += 1
            self.add_literal_level(level)
            self.update_s_mutex(self.s_levels[level])

            if self.s_levels[level] == self.s_levels[level - 1]:
                leveled = True

    def add_action_level(self, level):
        """ add an A (action) level to the Planning Graph

        :param level: int
            the level number alternates S0, A0, S1, A1, S2, .... etc the level number is also used as the
            index for the node set lists self.a_levels[] and self.s_levels[]
        :return:
            adds A nodes to the current level in self.a_levels[level]
        """
        # TODO add action A level to the planning graph as described in the Russell-Norvig text
        # 1. determine what actions to add and create those PgNode_a objects
        # 2. connect the nodes to the previous S literal level
        # for example, the A0 level will iterate through all possible actions for the problem and add a PgNode_a to a_levels[0]
        #   set iff all prerequisite literals for the action hold in S0.  This can be accomplished by testing
        #   to see if a proposed PgNode_a has prenodes that are a subset of the previous S level.  Once an
        #   action node is added, it MUST be connected to the S node instances in the appropriate s_level set.

        self.a_levels.append(set())
        # print("level inside the add_action_level",level)
        action_nodes_add=set()

        # for node in self.s_levels[level]:
            # print("node symbol and arg",node.symbol, node.is_pos)
        # print("\n")
        for action in self.all_actions:
            # print("The action",action)
            # print("action precondition pos",action.precond_pos)
            # print("action precondition neg",action.precond_neg)
            # print("action effect_add",action.effect_add)
            # print("action effect_rem",action.effect_rem)
            # is_Possible=True
            # input('')
            #
            action_node=PgNode_a(action)
            # print("action_node and its prenodes")
            # action_node.show()
            # for pre in action_node.prenodes:
            #     pre.show()
            # input('')
            if action_node.prenodes.issubset(self.s_levels[level]):

                #Then all of the precondtions of the action_node appear in the s_level
                # print("It is a subset")
                # input('')
                # print("action_nodes_add",action_nodes_add,type(action_nodes_add),"action_node",action_node,type(action_node))
                action_nodes_add.add(action_node)
                # print("Added to nodes to add")
                #Now need to populate the children and parents for the nodes in the previous s literal_list and the new action
                for prev_s_node in self.s_levels[level]:
                    # print("here")
                    # input('')
                    if prev_s_node in action_node.prenodes:
                        # print("the previous node is in the prenodes")
                        action_node.parents.add(prev_s_node)
                        prev_s_node.children.add(action_node)
                        # print(action_node.parents,prev_s_node.children)
                    # print("here 2")
                    # input('')


        # print("Adding those nodes to the a_levels")
        self.a_levels[level]=action_nodes_add
        # print("Success, Going to show the nodes now:")
        # input('')
        # print("Nodes of S0")
        # for node in self.s_levels[level]:
        #     node.show()
        # print("\nNodes of A",level)
        # for node in self.a_levels[level]:
        #     node.show()
        #
        # input('')
            # Check if all its positve preconditions are met in the previous state
            #
            # for action_precondition in action.precond_pos:
            #     if action_precondition not in self.s_levels[level].symbol:
            #         #Need to see if the precondition is in the list of sybols of the previous S literal
            #         is_Possible = False
            #
            #     if action_precondition in self.s_levels[level].symbol and self.s_levels[level].is_pos != True:
            #         # Need to try find a way to check if that symbol appears in the literal and its corresponding value is True
            #         is_Possible = False


            # Check if all its negative preconditions are met in the previous state
            # for pos_neg in action.precond_neg:
            #     if pos_neg not in self.fs.neg:
            #         is_Possible = False
            #
            # # If both positive and negative preconditions are met
            # if is_Possible:
            #     # print("Appending action")
            #     possible_actions.append(action)
            #     to_add=PgNode_a(action)



    def add_literal_level(self, level):
        """ add an S (literal) level to the Planning Graph

        :param level: int
            the level number alternates S0, A0, S1, A1, S2, .... etc the level number is also used as the
            index for the node set lists self.a_levels[] and self.s_levels[]
        :return:
            adds S nodes to the current level in self.s_levels[level]
        """
        # TODO add literal S level to the planning graph as described in the Russell-Norvig text
        # 1. determine what literals to add
        # 2. connect the nodes
        # for example, every A node in the previous level has a list of S nodes in effnodes that represent the effect
        #   produced by the action.  These literals will all be part of the new S level.  Since we are working with sets, they
        #   may be "added" to the set without fear of duplication.  However, it is important to then correctly create and connect
        #   all of the new S nodes as children of all the A nodes that could produce them, and likewise add the A nodes to the
        #   parent sets of the S nodes

        self.s_levels.append(set())
        s_literals_to_add=set()

        # print("Adding literals to level",level)
        for action_node in self.a_levels[level-1]:
            # print("node.action",node.action)
            # print("node.prenodes",node.prenodes)
            # print("node.effnodes",node.effnodes)

            for effect in action_node.effnodes:
                # print("The effect node symbol and is_pos ", effect.symbol,effect.is_pos)
                # print("adding it into the s_level")
                if effect not in s_literals_to_add:
                    # print("here")
                    # input('')
                    new_s_node=PgNode_s(effect.symbol, effect.is_pos)
                    s_literals_to_add.add(new_s_node)
                    new_s_node.parents.add(action_node)
                    action_node.children.add(new_s_node)
                    # print("here2")
                    # input('')
                else:
                    for s_node in s_literals_to_add:
                        # print("here3")
                        # input('')
                        if s_node==effect:
                            # print("here4")
                            # input('')
                            s_node.parents.add(action_node)
                            action_node.children.add(s_node)
                            # print("here5")
                            # input('')
                # if self.s_levels[level]: print("It is here")
                # else: print("doesnt exitst")

                # effect.show()
                # input('')

        self.s_levels[level]=s_literals_to_add
        # print("\nNodes in the action level")
        # for node in self.a_levels[level-1]:
        #     node.show()
        # print("\nNodes in the new S level", level)
        # for node in self.s_levels[level]:
        #     node.show()
        # input('')
        # for literal in self.fs.pos:
        #     self.s_levels[level].add(PgNode_s(literal, True))
        # for literal in self.fs.neg:
        #     self.s_levels[level].add(PgNode_s(literal, False))

    def update_a_mutex(self, nodeset):
        """ Determine and update sibling mutual exclusion for A-level nodes

        Mutex action tests section from 3rd Ed. 10.3 or 2nd Ed. 11.4
        A mutex relation holds between two actions a given level
        if the planning graph is a serial planning graph and the pair are nonpersistence actions
        or if any of the three conditions hold between the pair:
           Inconsistent Effects
           Interference
           Competing needs

        :param nodeset: set of PgNode_a (siblings in the same level)
        :return:
            mutex set in each PgNode_a in the set is appropriately updated
        """
        nodelist = list(nodeset)
        for i, n1 in enumerate(nodelist[:-1]):
            for n2 in nodelist[i + 1:]:
                if (self.serialize_actions(n1, n2) or
                        self.inconsistent_effects_mutex(n1, n2) or
                        self.interference_mutex(n1, n2) or
                        self.competing_needs_mutex(n1, n2)):
                    mutexify(n1, n2)

    def serialize_actions(self, node_a1: PgNode_a, node_a2: PgNode_a) -> bool:
        """
        Test a pair of actions for mutual exclusion, returning True if the
        planning graph is serial, and if either action is persistent; otherwise
        return False.  Two serial actions are mutually exclusive if they are
        both non-persistent.

        :param node_a1: PgNode_a
        :param node_a2: PgNode_a
        :return: bool
        """
        #
        if not self.serial:
            return False
        if node_a1.is_persistent or node_a2.is_persistent:
            return False
        return True

    def inconsistent_effects_mutex(self, node_a1: PgNode_a, node_a2: PgNode_a) -> bool:
        """
        Test a pair of actions for inconsistent effects, returning True if
        one action negates an effect of the other, and False otherwise.

        HINT: The Action instance associated with an action node is accessible
        through the PgNode_a.action attribute. See the Action class
        documentation for details on accessing the effects and preconditions of
        an action.

        :param node_a1: PgNode_a
        :param node_a2: PgNode_a
        :return: bool
        """
        # TODO test for Inconsistent Effects between nodes
        # print("node_a1 is ", node_a1.action)
        # print("node_a2 is ", node_a2.action)
        for node_1 in node_a1.effnodes:
            for node_2 in node_a2.effnodes:
                # print("node_a1.effnodes",node_1.symbol,node_1.is_pos)
                # print("node_a2.effnodes",node_2.symbol,node_2.is_pos)
                if node_1.symbol == node_2.symbol and node_1.is_pos !=node_2.is_pos:
                    # print("Symbols are the same, but they are opposite, returning True")
                    # input('')
                    return True

        # input('')
        return False

    def interference_mutex(self, node_a1: PgNode_a, node_a2: PgNode_a) -> bool:
        """
        Test a pair of actions for mutual exclusion, returning True if the
        effect of one action is the negation of a precondition of the other.

        HINT: The Action instance associated with an action node is accessible
        through the PgNode_a.action attribute. See the Action class
        documentation for details on accessing the effects and preconditions of
        an action.

        :param node_a1: PgNode_a
        :param node_a2: PgNode_a
        :return: bool
        """
        # TODO test for Interference between nodes
        # Check Node_a1s effects against a2's pre conditions
        for node_1 in node_a1.effnodes:
            for node_2 in node_a2.prenodes:
                if node_1.symbol == node_2.symbol and node_1.is_pos !=node_2.is_pos:
                    return True

        # and node 2's effects against node 1s preconditions
        for node_2 in node_a2.effnodes:
            for node_1 in node_a1.prenodes:
                if node_1.symbol == node_2.symbol and node_1.is_pos !=node_2.is_pos:
                    return True

        return False

    def competing_needs_mutex(self, node_a1: PgNode_a, node_a2: PgNode_a) -> bool:
        """
        Test a pair of actions for mutual exclusion, returning True if one of
        the precondition of one action is mutex with a precondition of the
        other action.

        :param node_a1: PgNode_a
        :param node_a2: PgNode_a
        :return: bool
        """

        # TODO test for Competing Needs between nodes
        # print("\nEntering in competing needs:")
        # print("node 1",node_a1.action)
        # print("node 2",node_a2.action)
        # print("Going in")
        for node_1 in node_a1.parents:
            for node_2 in node_a2.parents:
                # if node_1.symbol == node_2.symbol and node_1.symbol!=node_2.symbol:
                #     print("node_1",node_1.symbol,node_1.is_pos)
                #     print("node_2",node_2.symbol,node_2.is_pos)
                #     print("Same symbol, opposite sign")
                #     input('')
                if node_1.is_mutex(node_2):
                    # print("Mutex")
                    return True

                # input('')
        # print("None of the above have competing needs")
        # input('')
        # print("\n")
        return False

    def update_s_mutex(self, nodeset: set):
        """ Determine and update sibling mutual exclusion for S-level nodes

        Mutex action tests section from 3rd Ed. 10.3 or 2nd Ed. 11.4
        A mutex relation holds between literals at a given level
        if either of the two conditions hold between the pair:
           Negation
           Inconsistent support

        :param nodeset: set of PgNode_a (siblings in the same level)
        :return:
            mutex set in each PgNode_a in the set is appropriately updated
        """
        nodelist = list(nodeset)
        for i, n1 in enumerate(nodelist[:-1]):
            for n2 in nodelist[i + 1:]:
                if self.negation_mutex(n1, n2) or self.inconsistent_support_mutex(n1, n2):
                    mutexify(n1, n2)

    def negation_mutex(self, node_s1: PgNode_s, node_s2: PgNode_s) -> bool:
        """
        Test a pair of state literals for mutual exclusion, returning True if
        one node is the negation of the other, and False otherwise.

        HINT: Look at the PgNode_s.__eq__ defines the notion of equivalence for
        literal expression nodes, and the class tracks whether the literal is
        positive or negative.

        :param node_s1: PgNode_s
        :param node_s2: PgNode_s
        :return: bool
        """
        # TODO test for negation between nodes
        if node_s1.symbol == node_s2.symbol and node_s1.is_pos!=node_s2.is_pos:
            return True
        return False

    def inconsistent_support_mutex(self, node_s1: PgNode_s, node_s2: PgNode_s):
        """
        Test a pair of state literals for mutual exclusion, returning True if
        there are no actions that could achieve the two literals at the same
        time, and False otherwise.  In other words, the two literal nodes are
        mutex if all of the actions that could achieve the first literal node
        are pairwise mutually exclusive with all of the actions that could
        achieve the second literal node.

        HINT: The PgNode.is_mutex method can be used to test whether two nodes
        are mutually exclusive.

        :param node_s1: PgNode_s
        :param node_s2: PgNode_s
        :return: bool
        """
        # TODO test for Inconsistent Support between nodes
        for action1 in node_s1.parents:
            for action2 in node_s2.parents:

                if not action1.is_mutex(action2):
                    # action1.show()
                    # action2.show()
                    return False
        return True

    def h_levelsum(self) -> int:
        """The sum of the level costs of the individual goals (admissible if goals independent)

        :return: int
        """
        level_sum = 0
        # TODO implement
        # for each goal in the problem, determine the level cost, then add them together
        for goal in self.problem.goal:
            # print("goal",goal)
            goal_s=PgNode_s(goal,True)
            # reached=False
            for level_counter,s_state in enumerate(self.s_levels):

                # for node in s_state:
                #     print("node",node.symbol)
                if goal_s in s_state:
                    # reached=True
                    level_sum+=level_counter
                    break

        return level_sum
