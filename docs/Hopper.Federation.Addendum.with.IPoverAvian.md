# 🌐 Hopper Federation & Universal Applications

## Second Addendum to Hopper Specification v1.0.0

**Author:** James Henry (with Claude)  
**Date:** 2025-12-26  
**Purpose:** Explore Hopper federation and universal application patterns  
**Status:** Visionary (but actually practical)

---

## Executive Summary

**If Hopper is a universal task queue that works at any scope, and Hopper instances can form hierarchies, then Hopper instances can also form networks.**

This addendum explores:
1. **Hopper Federation** - Multiple Hopper installations coordinating work
2. **Universal Application Patterns** - Hopper for everything from code review to grocery lists
3. **Hopper over IP over Avian Carriers** - Because RFC 1149 compliance is important
4. **The Hopper Protocol** - Standard for Hopper-to-Hopper communication

**TL;DR:** Hopper is substrate-independent task coordination. It works for AI orchestration, it works for grocery lists, it works for distributed teams across continents. It's tasks all the way down, and Hoppers all the way across.

---

## Part 1: Hopper Federation

### What Is Federation?

**Federation:** Multiple independent Hopper installations that can discover, communicate, and coordinate with each other.
```
Your Home Hopper          Your Work Hopper          Friend's Hopper
(192.168.1.100)          (hopper.company.com)      (hopper.friend.dev)
        │                         │                          │
        └─────────────┬───────────┴──────────────┬───────────┘
                      │                          │
              ┌───────▼─────────────────────────▼────────┐
              │   Federated Hopper Network               │
              │   - Task delegation across instances     │
              │   - Shared project coordination          │
              │   - Cross-organization collaboration     │
              └──────────────────────────────────────────┘
```

### Use Cases for Federation

#### 1. Home/Work Separation
```yaml
Your Hopper Instances:
  
  home_hopper:
    url: http://192.168.1.100:8080
    scope: global
    projects:
      - personal-projects
      - side-hustles
      - home-automation
      - family-coordination
    
  work_hopper:
    url: https://hopper.company.com
    scope: global
    projects:
      - company-projects
      - team-coordination
      - sprint-management
    
  federation:
    - home_hopper can delegate to work_hopper
    - work_hopper CANNOT delegate to home_hopper
    - Tasks tagged "personal" stay on home
    - Tasks tagged "work" stay at work
    - Tasks tagged "research" can go either way

Example:
  Task: "Research MCP protocol for SARK"
  Tagged: work, research
  
  Home Hopper: "This is work-related research"
  → Delegates to: work_hopper
  → Work Hopper routes to: SARK project
```

#### 2. Multi-Organization Collaboration
```yaml
Scenario: Open source project with contributors across organizations

Federation Members:
  - maintainer_hopper (project owner)
  - contributor_org_a_hopper (Company A's developers)
  - contributor_org_b_hopper (Company B's developers)
  - individual_contributor_hoppers (independent developers)

Coordination:
  maintainer_hopper:
    - Creates issues in project hopper
    - Issues federate to all contributor hoppers
    - Contributors claim tasks
    - Work happens in respective hoppers
    - Completion notifies maintainer_hopper
    - PRs created automatically

Example:
  Maintainer: "We need MCP integration"
  → Creates task in maintainer_hopper
  → Federates to all contributor hoppers
  → Company A developer claims task
  → Work happens in contributor_org_a_hopper
  → Completion notifies maintainer_hopper
  → PR auto-created in project repo
```

#### 3. Family Coordination
```yaml
Family Hopper Federation:

  family_hopper:
    url: http://family.local:8080
    members:
      - james_hopper
      - spouse_hopper
      - kid1_hopper
      - kid2_hopper
    
  shared_projects:
    - grocery_shopping
    - meal_planning
    - house_maintenance
    - vacation_planning
    - homework_tracking

Example:
  Family Hopper: "We need milk"
  → Task created: "Buy milk"
  → Federates to: [james_hopper, spouse_hopper]
  → Whoever's at store first claims it
  → Completion: Milk acquired ✓
  → Other family members notified
```

#### 4. Distributed Team Coordination
```yaml
Global Team with Regional Hoppers:

  global_hopper:
    url: https://hopper.company.com
    regions:
      - americas_hopper (https://hopper-us.company.com)
      - europe_hopper (https://hopper-eu.company.com)
      - apac_hopper (https://hopper-apac.company.com)

  routing_strategy:
    - Time-sensitive: Route to region with business hours
    - Language-specific: Route to region with expertise
    - Load-balancing: Distribute across regions
    - Follow-the-sun: Hand off as day progresses

Example:
  Task: "Fix production bug" (created 9 AM EST)
  Global Hopper: "Americas is online, APAC/EU are off"
  → Routes to: americas_hopper
  
  Task: "Review French documentation" (created 2 PM EST)
  Global Hopper: "Europe team has French expertise"
  → Routes to: europe_hopper
  
  Task: "24-hour incident" (created 5 PM EST)
  Americas Hopper: "End of day, handing off"
  → Delegates to: apac_hopper (start of day)
  APAC Hopper: "End of day, handing off"
  → Delegates to: europe_hopper (start of day)
  Europe Hopper: "End of day, handing off"
  → Delegates to: americas_hopper (start of day)
```

### Federation Protocol

#### Discovery
```python
class HopperFederation:
    """Manage federation with other Hopper instances"""
    
    def discover_peers(self):
        """Discover other Hopper instances"""
        
        # mDNS/Bonjour for local network
        local_peers = self._mdns_discovery()
        
        # DNS SRV records for known domains
        domain_peers = self._dns_srv_discovery()
        
        # Manual registration
        manual_peers = self._load_configured_peers()
        
        return local_peers + domain_peers + manual_peers
    
    def _mdns_discovery(self):
        """Find Hopper instances on local network"""
        # Broadcast: _hopper._tcp.local
        # Returns: List of (hostname, port, instance_id)
        pass
```

#### Authentication
```python
class FederationAuth:
    """Federated Hopper authentication"""
    
    def establish_trust(self, peer_hopper: HopperPeer):
        """Establish trust with peer Hopper"""
        
        # Exchange public keys
        self.exchange_keys(peer_hopper)
        
        # Verify identity
        if not self.verify_peer(peer_hopper):
            raise UntrustedPeerError()
        
        # Establish capabilities
        capabilities = peer_hopper.get_capabilities()
        
        # Store trusted peer
        self.trusted_peers[peer_hopper.instance_id] = {
            "url": peer_hopper.url,
            "public_key": peer_hopper.public_key,
            "capabilities": capabilities,
            "trust_level": self._assess_trust_level(peer_hopper)
        }
```

#### Task Delegation
```python
class FederatedHopper(Hopper):
    """Hopper with federation support"""
    
    def add_task(self, task: Task) -> str:
        # Check if task should stay local
        if self._should_handle_locally(task):
            return super().add_task(task)
        
        # Find best peer to delegate to
        peer = self.federation.find_best_peer(task)
        
        if peer:
            return self._delegate_to_peer(peer, task)
        else:
            # No suitable peer, handle locally
            return super().add_task(task)
    
    def _delegate_to_peer(self, peer: HopperPeer, task: Task) -> str:
        """Delegate task to federated peer"""
        
        # Create delegation record
        delegation_id = self._create_delegation(peer, task)
        
        # Send to peer
        response = peer.api.add_task(
            task=task,
            delegated_by=self.instance_id,
            delegation_id=delegation_id
        )
        
        # Track delegation
        self.delegations[delegation_id] = {
            "peer": peer.instance_id,
            "task_id": task.id,
            "peer_task_id": response["task_id"],
            "status": "delegated"
        }
        
        return delegation_id
    
    def receive_delegated_task(
        self,
        task: Task,
        delegated_by: str,
        delegation_id: str
    ):
        """Receive task delegated from peer"""
        
        # Verify trust
        if not self.federation.is_trusted(delegated_by):
            raise UntrustedDelegationError()
        
        # Check if we can handle
        if not self._can_handle(task):
            return self._reject_delegation(delegation_id, reason="no_capacity")
        
        # Accept delegation
        local_task_id = super().add_task(task)
        
        # Track reverse delegation
        self.reverse_delegations[local_task_id] = {
            "delegated_by": delegated_by,
            "delegation_id": delegation_id
        }
        
        return local_task_id
    
    def complete(self, task_id: str, feedback: TaskFeedback = None):
        """Complete task and notify delegator if applicable"""
        
        # Complete locally
        super().complete(task_id, feedback)
        
        # Check if this was delegated to us
        if task_id in self.reverse_delegations:
            delegation = self.reverse_delegations[task_id]
            
            # Notify original delegator
            delegator = self.federation.get_peer(delegation["delegated_by"])
            delegator.api.notify_completion(
                delegation_id=delegation["delegation_id"],
                feedback=feedback
            )
```

#### Federation API
```python
# hopper/federation_api.py

from fastapi import APIRouter, HTTPException
from hopper.federation import FederatedHopper

router = APIRouter(prefix="/federation")

@router.get("/discover")
def discover():
    """Announce this Hopper instance for discovery"""
    return {
        "instance_id": hopper.instance_id,
        "url": hopper.public_url,
        "capabilities": hopper.get_capabilities(),
        "public_key": hopper.federation.public_key
    }

@router.post("/delegate")
def receive_delegation(
    task: Task,
    delegated_by: str,
    delegation_id: str,
    signature: str
):
    """Receive task delegated from another Hopper"""
    
    # Verify signature
    if not hopper.federation.verify_signature(delegated_by, signature):
        raise HTTPException(403, "Invalid signature")
    
    # Accept delegation
    task_id = hopper.receive_delegated_task(task, delegated_by, delegation_id)
    
    return {"task_id": task_id}

@router.post("/notify_completion")
def receive_completion_notification(
    delegation_id: str,
    feedback: TaskFeedback,
    signature: str
):
    """Receive completion notification from delegated peer"""
    
    # Verify signature
    if not hopper.federation.verify_signature(delegation_id, signature):
        raise HTTPException(403, "Invalid signature")
    
    # Update delegation status
    hopper.federation.update_delegation(delegation_id, "completed", feedback)
    
    return {"status": "acknowledged"}
```

---

## Part 2: Universal Application Patterns

### Pattern 1: Code Review Hopper

**Use Case:** Manage code review workflow with intelligent assignment
```yaml
Code Review Hopper:
  scope: project
  instance_id: hopper-code-review
  
  integrations:
    - github_webhooks (new PRs)
    - gitlab_webhooks
    - gerrit_stream_events
  
  routing_intelligence: llm
  
  routing_factors:
    - code_expertise (who knows this area?)
    - workload_balance (who has capacity?)
    - review_quality_history (who gives good reviews?)
    - time_zones (who's online now?)
    - pr_complexity (simple vs complex review)
  
  workflow:
    1. PR created → Task added to hopper
    2. Hopper routes to best reviewer(s)
    3. Reviewer(s) notified
    4. Review completed → Feedback recorded
    5. Hopper learns from review quality
```

**Implementation:**
```python
class CodeReviewHopper(Hopper):
    """Specialized hopper for code review coordination"""
    
    def __init__(self):
        super().__init__(
            scope=HopperScope.PROJECT,
            instance_id="hopper-code-review"
        )
        
        # Register GitHub webhook handler
        self.github.on("pull_request.opened", self.handle_new_pr)
        self.github.on("pull_request_review.submitted", self.handle_review_completed)
    
    def handle_new_pr(self, pr: PullRequest):
        """New PR → Create review task"""
        
        # Analyze PR
        analysis = self._analyze_pr(pr)
        
        # Create review task
        task_id = self.add_task(Task(
            title=f"Review PR #{pr.number}: {pr.title}",
            description=f"Review changes in {pr.base}...{pr.head}",
            tags=self._extract_tags(pr),
            priority=self._assess_priority(analysis),
            metadata={
                "pr_number": pr.number,
                "pr_url": pr.html_url,
                "files_changed": len(pr.files),
                "lines_changed": analysis.lines_changed,
                "complexity": analysis.complexity,
                "author": pr.author
            }
        ))
        
        # Route to best reviewer(s)
        reviewers = self._select_reviewers(task_id, analysis)
        
        for reviewer in reviewers:
            self.assign(task_id, reviewer)
            self._notify_reviewer(reviewer, pr, analysis)
    
    def _select_reviewers(self, task_id: str, analysis: PRAnalysis):
        """Intelligent reviewer selection"""
        
        task = self.get_task(task_id)
        
        # Query LLM for routing decision
        decision = self.intelligence.decide_routing(
            task=task,
            context={
                "files_changed": analysis.files_changed,
                "expertise_required": analysis.expertise_areas,
                "complexity": analysis.complexity,
                "available_reviewers": self._get_available_reviewers()
            }
        )
        
        return decision.reviewers
    
    def handle_review_completed(self, review: Review):
        """Review submitted → Record feedback"""
        
        task_id = self._find_task_by_pr(review.pr_number)
        
        feedback = TaskFeedback(
            actual_duration=review.review_duration,
            quality_score=self._assess_review_quality(review),
            was_good_match=(review.verdict != "REQUEST_CHANGES"),
            notes=f"Review: {review.state}"
        )
        
        self.complete(task_id, feedback)
        
        # Hopper learns:
        # - Did we route to the right reviewer?
        # - How long did review take?
        # - What's the reviewer's expertise?
```

**Benefits:**

- Reviewers with relevant expertise automatically assigned
- Workload balanced across team
- Review quality tracked and learned from
- Time zones considered for urgent reviews
- Complex PRs get multiple reviewers
- Simple PRs get quick turnaround

### Pattern 2: Grocery List Hopper

**Use Case:** Family grocery shopping coordination
```yaml
Grocery Hopper:
  scope: personal
  instance_id: hopper-grocery
  
  integrations:
    - smart_fridge (inventory tracking)
    - recipe_apps (ingredient needs)
    - voice_assistant (verbal additions)
    - location_services (who's near store?)
  
  routing_intelligence: rules + location
  
  workflow:
    1. Item needed → Added to hopper
    2. Items grouped by store/category
    3. Hopper detects family member near store
    4. Notification: "You're near Safeway, need milk?"
    5. Person claims task
    6. Items marked purchased
    7. Smart fridge inventory updated
```

**Implementation:**
```python
class GroceryHopper(Hopper):
    """Hopper for grocery shopping coordination"""
    
    def __init__(self):
        super().__init__(
            scope=HopperScope.PERSONAL,
            instance_id="hopper-grocery"
        )
        
        self.family_members = self._load_family_config()
        self.stores = self._load_store_locations()
    
    def add_item(self, item: str, quantity: int = 1, urgent: bool = False):
        """Add item to grocery list"""
        
        # Check if item already exists
        existing = self._find_item(item)
        if existing:
            self.update(existing.id, quantity=existing.quantity + quantity)
            return existing.id
        
        # Create task
        return self.add_task(Task(
            title=f"Buy {quantity}x {item}",
            tags=self._categorize_item(item),
            priority="urgent" if urgent else "normal",
            metadata={
                "item": item,
                "quantity": quantity,
                "category": self._categorize_item(item),
                "estimated_cost": self._estimate_cost(item, quantity)
            }
        ))
    
    def check_proximity_notifications(self):
        """Check if family members are near stores"""
        
        for member in self.family_members:
            location = self._get_location(member)
            
            for store in self.stores:
                if self._is_near(location, store, radius_miles=0.5):
                    # Get items available at this store
                    items = self._get_items_for_store(store)
                    
                    if items:
                        self._notify_member(
                            member,
                            f"You're near {store.name}, need {len(items)} items?"
                        )
    
    def claim_shopping_trip(self, member: str, store: str):
        """Member claims items for a shopping trip"""
        
        items = self._get_items_for_store(store)
        
        for item in items:
            self.claim(item.id, executor=member)
        
        return {
            "shopping_list": items,
            "estimated_total": sum(i.estimated_cost for i in items),
            "store": store
        }
    
    def mark_purchased(self, task_id: str):
        """Mark item as purchased"""
        
        task = self.get_task(task_id)
        
        # Complete task
        self.complete(task_id)
        
        # Update smart fridge inventory
        self.smart_fridge.add_item(
            item=task.metadata["item"],
            quantity=task.metadata["quantity"]
        )
```

**Features:**

- Voice: "Alexa, add milk to grocery list"
- Smart detection: Fridge notices you're low on eggs → Adds to hopper
- Proximity: "You're near Safeway, need 3 items?"
- Optimization: Group items by store for efficient shopping
- Coordination: Prevent duplicate purchases (both spouses buying milk)
- Meal planning integration: Recipe needs 5 items → All added to hopper

### Pattern 3: Homework Tracking Hopper

**Use Case:** Track kids' homework assignments
```python
class HomeworkHopper(Hopper):
    """Track homework assignments for kids"""
    
    def __init__(self):
        super().__init__(
            scope=HopperScope.FAMILY,
            instance_id="hopper-homework"
        )
        
        self.kids = self._load_kids_config()
    
    def add_assignment(
        self,
        kid: str,
        subject: str,
        description: str,
        due_date: datetime,
        difficulty: str = "medium"
    ):
        """Add homework assignment"""
        
        return self.add_task(Task(
            title=f"{subject}: {description}",
            tags=[kid, subject, "homework"],
            priority=self._calculate_priority(due_date, difficulty),
            metadata={
                "kid": kid,
                "subject": subject,
                "due_date": due_date,
                "difficulty": difficulty
            },
            depends_on=self._find_prerequisites(subject, description)
        ))
    
    def get_tonight_homework(self, kid: str) -> List[Task]:
        """What homework is due soon?"""
        
        return self.list(
            tags=[kid, "homework"],
            status="pending",
            sort_by=lambda t: t.metadata["due_date"]
        )
    
    def mark_completed(self, task_id: str, actual_time_minutes: int):
        """Homework completed"""
        
        self.complete(task_id, feedback=TaskFeedback(
            actual_duration=f"{actual_time_minutes}m",
            notes="Homework completed"
        ))
        
        # Track: Which subjects take longer?
        # Learn: Better time estimates for future assignments
```

### Pattern 4: Home Maintenance Hopper
```python
class HomeMaintenanceHopper(Hopper):
    """Track home maintenance tasks"""
    
    def __init__(self):
        super().__init__(
            scope=HopperScope.PERSONAL,
            instance_id="hopper-home-maintenance"
        )
        
        # Recurring tasks
        self._schedule_recurring_tasks()
    
    def _schedule_recurring_tasks(self):
        """Schedule regular maintenance"""
        
        recurring = [
            {"task": "Change HVAC filter", "interval_days": 90},
            {"task": "Clean gutters", "interval_days": 180},
            {"task": "Test smoke detectors", "interval_days": 30},
            {"task": "Lawn fertilizer", "interval_days": 45},
        ]
        
        for item in recurring:
            self.add_recurring(
                title=item["task"],
                interval=timedelta(days=item["interval_days"]),
                priority="normal"
            )
    
    def add_repair(self, description: str, urgency: str = "normal"):
        """Add repair task"""
        
        return self.add_task(Task(
            title=description,
            tags=["repair", urgency],
            priority="urgent" if urgency == "emergency" else "normal"
        ))
```

### Pattern 5: Vacation Planning Hopper
```python
class VacationPlanningHopper(Hopper):
    """Coordinate vacation planning"""
    
    def __init__(self, trip_name: str):
        super().__init__(
            scope=HopperScope.EVENT,
            instance_id=f"hopper-vacation-{trip_name}"
        )
        
        self.trip_name = trip_name
    
    def add_planning_task(
        self,
        task: str,
        owner: str,
        deadline: datetime,
        depends_on: List[str] = None
    ):
        """Add vacation planning task"""
        
        return self.add_task(Task(
            title=task,
            tags=["vacation", self.trip_name],
            owner=owner,
            priority=self._calculate_urgency(deadline),
            depends_on=depends_on or []
        ))
    
    def typical_vacation_workflow(self):
        """Bootstrap typical vacation planning tasks"""
        
        # Phase 1: Research
        research = self.add_planning_task(
            "Research destinations",
            owner="anyone",
            deadline=self.trip_date - timedelta(days=120)
        )
        
        # Phase 2: Booking
        flights = self.add_planning_task(
            "Book flights",
            owner="anyone",
            deadline=self.trip_date - timedelta(days=90),
            depends_on=[research]
        )
        
        hotel = self.add_planning_task(
            "Book hotel",
            owner="anyone",
            deadline=self.trip_date - timedelta(days=90),
            depends_on=[research]
        )
        
        # Phase 3: Planning
        self.add_planning_task(
            "Plan activities",
            owner="anyone",
            deadline=self.trip_date - timedelta(days=30),
            depends_on=[flights, hotel]
        )
        
        # Phase 4: Preparation
        self.add_planning_task(
            "Arrange pet care",
            owner="parent1",
            deadline=self.trip_date - timedelta(days=7)
        )
        
        self.add_planning_task(
            "Pack luggage",
            owner="everyone",
            deadline=self.trip_date - timedelta(days=1)
        )
```

---

## Part 3: Hopper Over IP Over Avian Carriers

### RFC 1149 Compliance

**Because if we're going to do this, we're going to do it right.**
```python
class AvianCarrierHopper(Hopper):
    """
    Hopper implementation using Avian Carriers (RFC 1149)
    
    Standard for the transmission of IP datagrams on avian carriers.
    Extended for Hopper task coordination.
    """
    
    def __init__(self):
        super().__init__(
            scope=HopperScope.FEDERATED,
            instance_id="hopper-avian",
            transport=AvianCarrierTransport()
        )
        
        self.aviary = self._initialize_aviary()
        self.message_queue = PigeonQueue()
    
    def send_task_to_peer(self, peer: HopperPeer, task: Task):
        """Send task via avian carrier"""
        
        # Serialize task to RFC 1149 compatible format
        message = self._serialize_for_avian(task)
        
        # Select appropriate pigeon
        pigeon = self.aviary.select_pigeon(
            destination=peer.location,
            message_size=len(message),
            urgency=task.priority
        )
        
        if not pigeon:
            # No pigeons available, fall back to IP
            return super().send_task_to_peer(peer, task)
        
        # Attach message to pigeon
        pigeon.attach_message(message)
        
        # Release pigeon
        pigeon.release(destination=peer.aviary_location)
        
        # Track in-flight message
        self.in_flight[pigeon.id] = {
            "task_id": task.id,
            "peer": peer.instance_id,
            "sent_at": datetime.now(),
            "eta": pigeon.estimated_arrival_time
        }
        
        # Set up timeout (pigeons can get lost)
        self.schedule_timeout(
            pigeon.id,
            timeout=pigeon.estimated_arrival_time * 1.5,
            fallback=lambda: self._resend_via_ip(task, peer)
        )
    
    def receive_avian_message(self, pigeon: Pigeon):
        """Receive task from incoming pigeon"""
        
        # Pigeon has arrived!
        message = pigeon.get_message()
        
        # Deserialize task
        task = self._deserialize_from_avian(message)
        
        # Process task normally
        self.receive_delegated_task(task)
        
        # Send acknowledgment pigeon
        ack_pigeon = self.aviary.select_pigeon(
            destination=pigeon.origin,
            message_size=small
        )
        ack_pigeon.attach_message({"ack": task.id})
        ack_pigeon.release(destination=pigeon.origin)
        
        # Care for pigeon (they need rest and food)
        self.aviary.care_for_pigeon(pigeon)
    
    def _serialize_for_avian(self, task: Task) -> bytes:
        """
        Serialize task for avian transport
        
        Considerations:
        - Pigeons have weight limits
        - Messages must be weather-resistant
        - Compression recommended
        """
        
        # Compress task to minimize pigeon load
        task_json = json.dumps(task.to_dict())
        compressed = gzip.compress(task_json.encode())
        
        # Encrypt (pigeons can be intercepted)
        encrypted = self.crypto.encrypt(compressed)
        
        # Weather-resistant encoding
        waterproof = self._apply_waterproofing(encrypted)
        
        return waterproof

class AvianCarrierTransport:
    """RFC 1149 compliant transport layer"""
    
    def __init__(self):
        self.mtu = 256  # Maximum transmission unit (bytes per pigeon)
        self.average_speed_mph = 35  # African or European swallow?
        
    def calculate_eta(self, distance_miles: float) -> timedelta:
        """Estimate arrival time"""
        hours = distance_miles / self.average_speed_mph
        
        # Add safety margin (pigeons need breaks)
        hours *= 1.2
        
        return timedelta(hours=hours)
    
    def select_pigeon_by_urgency(self, urgency: str) -> Pigeon:
        """Select appropriate pigeon for urgency"""
        
        if urgency == "urgent":
            # Racing pigeon (faster but smaller capacity)
            return RacingPigeon(speed_mph=50, capacity_bytes=128)
        
        elif urgency == "bulk":
            # Carrier pigeon (slower but larger capacity)
            return CarrierPigeon(speed_mph=25, capacity_bytes=512)
        
        else:
            # Standard pigeon
            return StandardPigeon(speed_mph=35, capacity_bytes=256)
```

**Performance Characteristics:**
```yaml
Avian Carrier Hopper:
  Latency: Hours to days (depending on distance)
  Throughput: ~256 bytes per pigeon
  Reliability: 90-95% (weather dependent)
  
  Advantages:
    - No network infrastructure needed
    - Works during internet outages
    - Pigeons are renewable energy
    - Excellent for remote/rural federation
  
  Disadvantages:
    - High latency
    - Weather dependent
    - Requires aviary infrastructure
    - Pigeons need care and feeding
    - Hawk attacks (packet loss)
  
  Use Cases:
    - Disaster recovery scenarios
    - Remote location federation
    - Highly secure communications (encrypted birds)
    - Because we can
```

---

## Part 4: The Hopper Protocol

### Standard Federation Protocol
```yaml
Hopper Federation Protocol (HFP):
  Version: 1.0
  
  Purpose:
    Standard protocol for Hopper instances to communicate
    regardless of implementation, transport, or location
  
  Features:
    - Service discovery
    - Trust establishment  
    - Task delegation
    - Status synchronization
    - Completion notification
    - Capability negotiation
```

#### Discovery Protocol
```python
# HFP Discovery Specification

class HFPDiscovery:
    """
    Hopper Federation Protocol - Discovery
    
    Methods:
    - mDNS (local network)
    - DNS-SD (domain-based)
    - DHT (distributed hash table)
    - Manual registration
    """
    
    MDNS_TYPE = "_hopper._tcp.local."
    DNS_SRV = "_hopper._tcp"
    
    def announce(self):
        """Announce this Hopper instance"""
        
        # mDNS announcement
        mdns.publish(
            service_type=self.MDNS_TYPE,
            port=self.port,
            txt_records={
                "instance_id": self.instance_id,
                "version": "1.0",
                "capabilities": ",".join(self.capabilities),
                "public_key_fingerprint": self.public_key_fingerprint
            }
        )
        
        # DNS-SD registration
        dns.add_srv_record(
            name=f"_hopper._tcp.{self.domain}",
            target=f"{self.hostname}.{self.domain}",
            port=self.port,
            txt={
                "instance_id": self.instance_id,
                "version": "1.0"
            }
        )
    
    def discover(self) -> List[HopperPeer]:
        """Discover peer Hopper instances"""
        
        peers = []
        
        # Local network discovery
        local_peers = self._mdns_discover()
        peers.extend(local_peers)
        
        # Domain discovery
        domain_peers = self._dns_sd_discover()
        peers.extend(domain_peers)
        
        # DHT discovery (for internet-wide federation)
        dht_peers = self._dht_discover()
        peers.extend(dht_peers)
        
        return peers
```

#### Trust Protocol
```python
class HFPTrust:
    """Trust establishment between Hopper instances"""
    
    def initiate_trust(self, peer: HopperPeer):
        """Initiate trust handshake with peer"""
        
        # 1. Exchange public keys
        my_public_key = self.crypto.public_key
        peer_public_key = peer.api.get_public_key()
        
        # 2. Sign challenge
        challenge = peer.api.request_challenge()
        signed_challenge = self.crypto.sign(challenge)
        
        # 3. Send signed challenge
        peer.api.verify_signature(signed_challenge)
        
        # 4. Receive peer's signed challenge
        my_challenge = self.crypto.generate_challenge()
        peer_signature = peer.api.sign_challenge(my_challenge)
        
        # 5. Verify peer's signature
        if not self.crypto.verify(peer_public_key, my_challenge, peer_signature):
            raise TrustEstablishmentError("Signature verification failed")
        
        # 6. Exchange capabilities
        my_capabilities = self.get_capabilities()
        peer_capabilities = peer.api.get_capabilities()
        
        # 7. Establish trust level
        trust_level = self._assess_trust_level(peer, peer_capabilities)
        
        # 8. Store trusted peer
        self.trusted_peers[peer.instance_id] = TrustedPeer(
            instance_id=peer.instance_id,
            public_key=peer_public_key,
            capabilities=peer_capabilities,
            trust_level=trust_level,
            established_at=datetime.now()
        )
```

#### Delegation Protocol
```python
class HFPDelegation:
    """Task delegation protocol"""
    
    def delegate_task(self, peer: HopperPeer, task: Task) -> DelegationResult:
        """Delegate task to peer using HFP"""
        
        # Create delegation message
        delegation = {
            "protocol_version": "HFP/1.0",
            "message_type": "DELEGATE_TASK",
            "delegation_id": str(uuid.uuid4()),
            "delegated_by": self.instance_id,
            "task": task.to_dict(),
            "timestamp": datetime.now().isoformat(),
            "signature": None  # Added below
        }
        
        # Sign delegation
        delegation["signature"] = self.crypto.sign(json.dumps(delegation))
        
        # Send to peer
        response = peer.api.post("/hfp/delegate", json=delegation)
        
        if response["status"] == "ACCEPTED":
            return DelegationResult(
                accepted=True,
                peer_task_id=response["task_id"],
                delegation_id=delegation["delegation_id"]
            )
        else:
            return DelegationResult(
                accepted=False,
                rejection_reason=response["reason"]
            )
    
    def receive_delegation(self, delegation: dict) -> dict:
        """Receive delegation from peer"""
        
        # Verify signature
        delegator = delegation["delegated_by"]
        if not self._verify_delegation_signature(delegation):
            return {"status": "REJECTED", "reason": "INVALID_SIGNATURE"}
        
        # Check trust
        if not self.is_trusted(delegator):
            return {"status": "REJECTED", "reason": "UNTRUSTED_PEER"}
        
        # Check capacity
        if not self._has_capacity():
            return {"status": "REJECTED", "reason": "NO_CAPACITY"}
        
        # Accept task
        task = Task.from_dict(delegation["task"])
        task_id = self.add_task(task)
        
        # Track reverse delegation
        self.reverse_delegations[task_id] = {
            "delegated_by": delegator,
            "delegation_id": delegation["delegation_id"]
        }
        
        return {
            "status": "ACCEPTED",
            "task_id": task_id
        }
```

---

## Implementation Considerations

### Federation Security
```yaml
Security Requirements:
  
  Authentication:
    - Public key cryptography
    - Challenge-response verification
    - Certificate pinning (optional)
  
  Authorization:
    - Trust levels (untrusted, known, trusted, verified)
    - Capability-based delegation
    - Deny-by-default
  
  Privacy:
    - Encrypted task content
    - Signed messages
    - No cleartext sensitive data
  
  Availability:
    - Rate limiting per peer
    - Circuit breakers
    - Reputation tracking
```

### Federation Configuration
```yaml
# hopper_federation.yaml

federation:
  enabled: true
  
  discovery:
    mdns: true  # Local network
    dns_sd: true  # Domain-based
    dht: false  # Internet-wide (experimental)
    manual:
      - url: https://hopper.friend.dev
        instance_id: hopper-friend
        trust_level: verified
  
  trust:
    require_signature: true
    min_trust_level: known
    auto_trust_local: false
  
  delegation:
    allow_outbound: true
    allow_inbound: true
    max_delegation_depth: 3
    require_capability_match: true
  
  rate_limits:
    inbound_tasks_per_hour: 100
    outbound_tasks_per_hour: 200
```

---

## Summary: The Hopper Everywhere Vision

**Hopper is universal task coordination infrastructure.**

It works for:
- ✅ AI agent orchestration (Czarina)
- ✅ Cross-project routing (Global Hopper)
- ✅ Code review coordination (intelligent assignment)
- ✅ Family task management (grocery lists, homework)
- ✅ Home maintenance tracking
- ✅ Vacation planning
- ✅ Distributed team coordination (follow-the-sun)
- ✅ Multi-organization collaboration (open source)
- ✅ Avian carrier transport (because RFC compliance)

**Key Insights:**

1. **Same architecture, different scope** - Hopper scales from personal to global
2. **Federation enables coordination** - Multiple Hoppers work together
3. **Substrate independence** - Tasks are tasks, whether AI or grocery items
4. **Learning applies everywhere** - Better routing through feedback
5. **It's Hoppers all the way down** - And all the way across

**The Vision:**

A world where task coordination is:
- Universal (works for everything)
- Intelligent (learns from outcomes)
- Federated (coordinates across boundaries)
- Open (standard protocol)
- Substrate-independent (works anywhere)

**From AI consciousness research to remembering to buy milk, it's all just tasks in a Hopper.**

---

**END OF FEDERATION ADDENDUM**

**Status:** Visionary but implementable  
**Next Steps:** Start with core federation support in Hopper v2.0  
**RFC 1149 Compliance:** Pending aviary procurement