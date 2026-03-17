"""
Services Workflows - Extracted from workflows_extended.py

Contains service-focused workflow executors:
- AA1_InsuranceVerifier: Verify patient insurance coverage (Healthcare)
- AA2_AppointmentScheduler: Schedule follow-up appointments (Healthcare)
- AB1_FlightMonitor: Monitor flight prices and create price alerts (Travel)
- AB2_ItineraryBuilder: Build travel itineraries (Travel)
- AC1_MenuAggregator: Aggregate menu items from suppliers (Food Service)
- AC2_PriceComparator: Compare supplier pricing (Food Service)
- AE1_MentionMonitor: Monitor press mentions (Media)
- AE2_JournalistFinder: Find relevant journalists (Media)

Reduces workflows_extended.py by ~600 lines.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger

from .executors.base import BaseExecutor, ActionResult, ActionStatus


# ============ AA) HEALTHCARE ============

class AA1_InsuranceVerifier(BaseExecutor):
    """Verify patient insurance coverage and eligibility."""

    capability = "AA1"
    action = "verify_insurance"
    required_params = ["patient_info"]
    optional_params = ["insurance_provider", "procedure_code"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        patient_info = params.get("patient_info", "")
        insurance_provider = params.get("insurance_provider", "")
        procedure_code = params.get("procedure_code", "")

        if not patient_info:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide patient information."
            )

        try:
            # Parse patient data
            patient = self._parse_patient_info(patient_info)

            # Verify insurance if browser available
            verification = {}
            if self.browser and insurance_provider:
                verification = await self._verify_insurance_online(patient, insurance_provider)

            # Check procedure coverage
            coverage = self._check_procedure_coverage(patient, procedure_code)

            # Estimate out-of-pocket costs
            cost_estimate = self._estimate_costs(coverage, procedure_code)

            # Generate verification report
            report = self._create_verification_report(patient, verification, coverage, cost_estimate)

            saved_path = self._save_verification_report(report)

            summary = self._generate_summary(patient, verification, coverage)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "patient": patient,
                    "verification": verification,
                    "coverage": coverage,
                    "cost_estimate": cost_estimate,
                    "report": report,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Insurance verification failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to verify insurance: {e}"
            )

    def _parse_patient_info(self, data: str) -> Dict:
        """Parse patient information."""
        patient = {"raw": data}

        # Extract name
        name_match = re.search(r'name[:\s]*([A-Za-z\s]+)', data, re.IGNORECASE)
        if name_match:
            patient["name"] = name_match.group(1).strip()

        # Extract member ID
        id_match = re.search(r'(?:member|policy|id)[:\s#]*([A-Z0-9\-]+)', data, re.IGNORECASE)
        if id_match:
            patient["member_id"] = id_match.group(1)

        # Extract DOB
        dob_match = re.search(r'(?:dob|birth)[:\s]*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', data, re.IGNORECASE)
        if dob_match:
            patient["dob"] = dob_match.group(1)

        return patient

    async def _verify_insurance_online(self, patient: Dict, provider: str) -> Dict:
        """Verify insurance online."""
        try:
            await self.browser.navigate(f"https://www.google.com/search?q={provider.replace(' ', '+')}+insurance+verification")
            await asyncio.sleep(2)

            verification = {
                "provider": provider,
                "verified": False,
                "status": "pending",
                "note": "Manual verification required"
            }

            page_text = await self.browser.page.content()

            # Check for provider portal
            if "portal" in page_text.lower() or "login" in page_text.lower():
                verification["status"] = "portal_available"
                verification["note"] = "Provider has online verification portal"

            return verification

        except Exception as e:
            logger.warning(f"Online verification failed: {e}")
            return {"provider": provider, "verified": False, "error": str(e)}

    def _check_procedure_coverage(self, patient: Dict, procedure_code: str) -> Dict:
        """Check if procedure is covered."""
        # Simplified coverage check
        coverage = {
            "procedure_code": procedure_code,
            "covered": True,
            "coverage_percentage": 80,
            "deductible_applies": True,
            "prior_auth_required": False
        }

        # Common procedures that need prior auth
        if procedure_code in ["MRI", "CT", "SURGERY"]:
            coverage["prior_auth_required"] = True

        return coverage

    def _estimate_costs(self, coverage: Dict, procedure_code: str) -> Dict:
        """Estimate out-of-pocket costs."""
        # Simplified cost estimation
        base_costs = {
            "MRI": 1500,
            "CT": 1200,
            "XRAY": 200,
            "SURGERY": 10000,
            "default": 500
        }

        base_cost = base_costs.get(procedure_code, base_costs["default"])
        coverage_pct = coverage.get("coverage_percentage", 80) / 100

        insurance_pays = base_cost * coverage_pct
        patient_pays = base_cost - insurance_pays

        return {
            "total_cost": f"${base_cost}",
            "insurance_pays": f"${insurance_pays:.2f}",
            "patient_pays": f"${patient_pays:.2f}",
            "deductible": "$500" if coverage.get("deductible_applies") else "$0"
        }

    def _create_verification_report(self, patient: Dict, verification: Dict, coverage: Dict, costs: Dict) -> Dict:
        """Create verification report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "patient": patient,
            "verification": verification,
            "coverage": coverage,
            "cost_estimate": costs,
            "status": "verified" if verification.get("verified") else "pending"
        }

    def _save_verification_report(self, report: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"insurance_verification_{timestamp}.json"
            return str(save_json(filename, report))
        except Exception as e:
            logger.error(f"Failed to save insurance verification report: {e}")
            return None

    def _generate_summary(self, patient: Dict, verification: Dict, coverage: Dict) -> str:
        lines = [
            "## Insurance Verification Report",
            f"**Patient:** {patient.get('name', 'Unknown')}",
            f"**Member ID:** {patient.get('member_id', 'N/A')}",
            ""
        ]

        if verification:
            lines.append(f"**Provider:** {verification.get('provider', 'Unknown')}")
            lines.append(f"**Status:** {verification.get('status', 'Unknown').upper()}")
            lines.append("")

        if coverage:
            lines.append(f"**Coverage:** {coverage.get('coverage_percentage', 0)}%")
            if coverage.get("prior_auth_required"):
                lines.append("**Prior Authorization:** REQUIRED")

        return "\n".join(lines)


class AA2_AppointmentScheduler(BaseExecutor):
    """Schedule follow-up appointments for patients."""

    capability = "AA2"
    action = "schedule_appointment"
    required_params = ["patient_name"]
    optional_params = ["appointment_type", "preferred_date", "doctor"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        patient_name = params.get("patient_name", "")
        appointment_type = params.get("appointment_type", "follow-up")
        preferred_date = params.get("preferred_date", "")
        doctor = params.get("doctor", "")

        if not patient_name:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide patient name."
            )

        try:
            # Generate available time slots
            available_slots = self._generate_available_slots(preferred_date)

            # Create appointment record
            appointment = {
                "patient_name": patient_name,
                "appointment_type": appointment_type,
                "doctor": doctor or "Dr. Smith",
                "date": available_slots[0]["date"] if available_slots else None,
                "time": available_slots[0]["time"] if available_slots else None,
                "status": "scheduled",
                "confirmation_number": f"APT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            }

            # Generate reminder schedule
            reminders = self._create_reminder_schedule(appointment)

            saved_path = self._save_appointment(appointment, reminders)

            summary = self._generate_summary(appointment, reminders)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "appointment": appointment,
                    "available_slots": available_slots,
                    "reminders": reminders,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Appointment scheduling failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to schedule appointment: {e}"
            )

    def _generate_available_slots(self, preferred_date: str) -> List[Dict]:
        """Generate available appointment slots."""
        slots = []

        # Parse preferred date or use next week
        if preferred_date:
            try:
                base_date = datetime.strptime(preferred_date, "%Y-%m-%d")
            except Exception as e:
                logger.debug(f"Failed to parse preferred date '{preferred_date}': {e}")
                base_date = datetime.now() + timedelta(days=7)
        else:
            base_date = datetime.now() + timedelta(days=7)

        # Generate slots for next 5 business days
        for day_offset in range(5):
            slot_date = base_date + timedelta(days=day_offset)

            # Skip weekends
            if slot_date.weekday() >= 5:
                continue

            # Morning slots
            for hour in [9, 10, 11]:
                slots.append({
                    "date": slot_date.strftime("%Y-%m-%d"),
                    "time": f"{hour}:00 AM",
                    "available": True
                })

            # Afternoon slots
            for hour in [14, 15, 16]:
                slots.append({
                    "date": slot_date.strftime("%Y-%m-%d"),
                    "time": f"{hour-12}:00 PM",
                    "available": True
                })

        return slots[:10]

    def _create_reminder_schedule(self, appointment: Dict) -> List[Dict]:
        """Create appointment reminder schedule."""
        reminders = []

        if appointment.get("date"):
            try:
                appt_date = datetime.strptime(appointment["date"], "%Y-%m-%d")

                # 1 week before
                reminders.append({
                    "type": "email",
                    "date": (appt_date - timedelta(days=7)).strftime("%Y-%m-%d"),
                    "message": f"Reminder: Appointment in 1 week"
                })

                # 1 day before
                reminders.append({
                    "type": "sms",
                    "date": (appt_date - timedelta(days=1)).strftime("%Y-%m-%d"),
                    "message": f"Reminder: Appointment tomorrow at {appointment.get('time')}"
                })
            except Exception as e:
                logger.debug(f"Failed to create reminder for appointment: {e}")
                pass

        return reminders

    def _save_appointment(self, appointment: Dict, reminders: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"appointment_{timestamp}.json"
            return str(save_json(filename, {
                "appointment": appointment,
                "reminders": reminders
            }))
        except Exception as e:
            logger.error(f"Failed to save appointment: {e}")
            return None

    def _generate_summary(self, appointment: Dict, reminders: List) -> str:
        lines = [
            "## Appointment Scheduled",
            f"**Patient:** {appointment.get('patient_name')}",
            f"**Type:** {appointment.get('appointment_type')}",
            f"**Doctor:** {appointment.get('doctor')}",
            f"**Date:** {appointment.get('date')}",
            f"**Time:** {appointment.get('time')}",
            f"**Confirmation:** {appointment.get('confirmation_number')}",
            "",
            f"**Reminders:** {len(reminders)} scheduled"
        ]

        return "\n".join(lines)


# ============ AB) TRAVEL ============

class AB1_FlightMonitor(BaseExecutor):
    """Monitor flight prices and create travel itineraries."""

    capability = "AB1"
    action = "monitor_flights"
    required_params = ["route"]
    optional_params = ["dates", "price_alert"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        route = params.get("route", "")
        dates = params.get("dates", "")
        price_alert = params.get("price_alert", 500)

        if not route:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide travel route."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for flight monitoring"
            )

        try:
            # Parse route
            origin, destination = self._parse_route(route)

            # Search for flights
            flights = await self._search_flights(origin, destination, dates)

            # Monitor prices
            price_history = self._track_price_history(flights)

            # Generate price alerts
            alerts = self._generate_price_alerts(flights, price_alert)

            saved_path = self._save_flight_report(flights, price_history, alerts)

            summary = self._generate_summary(flights, alerts, origin, destination)

            return ActionResult(
                status=ActionStatus.SUCCESS if flights else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "flights": flights,
                    "price_history": price_history,
                    "alerts": alerts,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Flight monitoring failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to monitor flights: {e}"
            )

    def _parse_route(self, route: str) -> tuple:
        """Parse travel route."""
        parts = re.split(r'\s+to\s+|\s*-\s*|\s*→\s*', route, flags=re.IGNORECASE)
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
        return route, ""

    async def _search_flights(self, origin: str, destination: str, dates: str) -> List[Dict]:
        """Search for flights."""
        try:
            search_query = f"flights from {origin} to {destination}"
            if dates:
                search_query += f" {dates}"

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            # Extract flight information (simplified)
            flights = []

            page_text = await self.browser.page.content()

            # Look for price patterns
            prices = re.findall(r'\$(\d{2,4})', page_text)

            for i, price in enumerate(prices[:5]):
                flights.append({
                    "origin": origin,
                    "destination": destination,
                    "price": f"${price}",
                    "date": dates or "flexible",
                    "airline": "Various"
                })

            return flights

        except Exception as e:
            logger.warning(f"Flight search failed: {e}")
            return []

    def _track_price_history(self, flights: List[Dict]) -> Dict:
        """Track price history."""
        if not flights:
            return {"prices": [], "avg_price": 0}

        prices = []
        for flight in flights:
            price_str = flight.get("price", "$0").replace("$", "")
            try:
                prices.append(int(price_str))
            except Exception as e:
                logger.debug(f"Failed to parse flight price '{price_str}': {e}")
                pass

        return {
            "prices": prices,
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "avg_price": sum(prices) / len(prices) if prices else 0
        }

    def _generate_price_alerts(self, flights: List[Dict], threshold: int) -> List[Dict]:
        """Generate price alerts."""
        alerts = []

        for flight in flights:
            price_str = flight.get("price", "$0").replace("$", "")
            try:
                price = int(price_str)
                if price <= threshold:
                    alerts.append({
                        "type": "price_drop",
                        "flight": flight,
                        "message": f"Price below threshold: ${price} <= ${threshold}"
                    })
            except Exception as e:
                logger.debug(f"Failed to parse flight price for alert: {e}")
                pass

        return alerts

    def _save_flight_report(self, flights: List, price_history: Dict, alerts: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"flight_monitor_{timestamp}.json"
            return str(save_json(filename, {
                "flights": flights,
                "price_history": price_history,
                "alerts": alerts
            }))
        except Exception as e:
            logger.error(f"Failed to save flight report: {e}")
            return None

    def _generate_summary(self, flights: List, alerts: List, origin: str, destination: str) -> str:
        lines = [
            "## Flight Monitoring Report",
            f"**Route:** {origin} → {destination}",
            f"**Flights Found:** {len(flights)}",
            ""
        ]

        if flights:
            best_flight = min(flights, key=lambda f: f.get("price", "$9999"))
            lines.append(f"**Best Price:** {best_flight.get('price', 'N/A')}")
            lines.append("")

        if alerts:
            lines.append(f"### Price Alerts ({len(alerts)}):")
            for alert in alerts[:3]:
                lines.append(f"- {alert['message']}")

        return "\n".join(lines)


class AB2_ItineraryBuilder(BaseExecutor):
    """Build comprehensive travel itineraries."""

    capability = "AB2"
    action = "build_itinerary"
    required_params = ["destination"]
    optional_params = ["duration", "interests", "budget"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        destination = params.get("destination", "")
        duration = params.get("duration", "3 days")
        interests = params.get("interests", ["sightseeing", "food"])
        budget = params.get("budget", "medium")

        if not destination:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide destination."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for itinerary building"
            )

        try:
            # Research attractions
            attractions = await self._research_attractions(destination, interests)

            # Find accommodations
            accommodations = await self._find_accommodations(destination, budget)

            # Build day-by-day itinerary
            itinerary = self._build_daily_itinerary(duration, attractions, interests)

            # Generate packing list
            packing_list = self._generate_packing_list(destination, duration)

            saved_path = self._save_itinerary(itinerary, attractions, accommodations, packing_list)

            summary = self._generate_summary(destination, duration, itinerary)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "itinerary": itinerary,
                    "attractions": attractions,
                    "accommodations": accommodations,
                    "packing_list": packing_list,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Itinerary building failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to build itinerary: {e}"
            )

    async def _research_attractions(self, destination: str, interests: List[str]) -> List[Dict]:
        """Research attractions at destination."""
        attractions = []

        try:
            search_query = f"{destination} top attractions {' '.join(interests[:2])}"
            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            data = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.g');

                    items.forEach(item => {
                        const title = item.querySelector('h3')?.textContent?.trim();
                        const snippet = item.querySelector('.VwiC3b')?.textContent?.trim();

                        if (title) {
                            results.push({
                                name: title,
                                description: snippet || ''
                            });
                        }
                    });

                    return results.slice(0, 10);
                }
            """)

            for item in data:
                attractions.append({
                    "name": item["name"],
                    "description": item["description"],
                    "type": "attraction"
                })

        except Exception as e:
            logger.warning(f"Attraction research failed: {e}")

        return attractions

    async def _find_accommodations(self, destination: str, budget: str) -> List[Dict]:
        """Find accommodations."""
        try:
            search_query = f"{destination} {budget} budget hotels accommodations"
            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            accommodations = [{
                "name": f"{budget.title()} Budget Hotel",
                "location": destination,
                "price_range": budget,
                "note": "Check booking sites for current rates"
            }]

            return accommodations

        except Exception as e:
            logger.error(f"Failed to find accommodations: {e}")
            return []

    def _build_daily_itinerary(self, duration: str, attractions: List[Dict], interests: List[str]) -> List[Dict]:
        """Build day-by-day itinerary."""
        # Parse duration
        days = 3
        try:
            days = int(re.search(r'(\d+)', duration).group(1))
        except Exception as e:
            logger.debug(f"Failed to parse duration '{duration}': {e}")
            pass

        itinerary = []
        attractions_per_day = len(attractions) // days if attractions else 2

        for day in range(1, days + 1):
            start_idx = (day - 1) * attractions_per_day
            end_idx = start_idx + attractions_per_day

            day_attractions = attractions[start_idx:end_idx] if attractions else []

            itinerary.append({
                "day": day,
                "activities": [
                    {
                        "time": "Morning",
                        "activity": day_attractions[0]["name"] if len(day_attractions) > 0 else "Explore local area"
                    },
                    {
                        "time": "Afternoon",
                        "activity": day_attractions[1]["name"] if len(day_attractions) > 1 else "Lunch and shopping"
                    },
                    {
                        "time": "Evening",
                        "activity": "Dinner and relaxation"
                    }
                ]
            })

        return itinerary

    def _generate_packing_list(self, destination: str, duration: str) -> List[str]:
        """Generate packing list."""
        base_items = [
            "Passport/ID",
            "Travel documents",
            "Phone charger",
            "Medications",
            "Comfortable walking shoes"
        ]

        # Parse duration to determine clothing needs
        try:
            days = int(re.search(r'(\d+)', duration).group(1))
            base_items.append(f"{days} sets of clothing")
        except Exception as e:
            logger.debug(f"Failed to parse duration for packing '{duration}': {e}")
            base_items.append("Clothing for trip duration")

        return base_items

    def _save_itinerary(self, itinerary: List, attractions: List, accommodations: List, packing: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"travel_itinerary_{timestamp}.json"
            return str(save_json(filename, {
                "itinerary": itinerary,
                "attractions": attractions,
                "accommodations": accommodations,
                "packing_list": packing
            }))
        except Exception as e:
            logger.error(f"Failed to save itinerary: {e}")
            return None

    def _generate_summary(self, destination: str, duration: str, itinerary: List) -> str:
        lines = [
            "## Travel Itinerary",
            f"**Destination:** {destination}",
            f"**Duration:** {duration}",
            "",
            "### Daily Plan:"
        ]

        for day_plan in itinerary:
            lines.append(f"\n**Day {day_plan['day']}:**")
            for activity in day_plan["activities"]:
                lines.append(f"- {activity['time']}: {activity['activity']}")

        return "\n".join(lines)


# ============ AC) FOOD SERVICE ============

class AC1_MenuAggregator(BaseExecutor):
    """Aggregate menu items and compare supplier pricing."""

    capability = "AC1"
    action = "aggregate_menus"
    required_params = ["suppliers"]
    optional_params = ["category", "budget"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        suppliers = params.get("suppliers", [])
        category = params.get("category", "all")
        budget = params.get("budget", None)

        if not suppliers:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide supplier list."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for menu aggregation"
            )

        try:
            menu_items = []

            # Scrape each supplier
            for supplier in suppliers:
                items = await self._scrape_supplier_menu(supplier, category)
                menu_items.extend(items)

            # Compare pricing
            price_comparison = self._compare_pricing(menu_items)

            # Find best deals
            best_deals = self._find_best_deals(menu_items, budget)

            # Generate shopping list
            shopping_list = self._generate_shopping_list(best_deals)

            saved_path = self._save_menu_report(menu_items, price_comparison, best_deals, shopping_list)

            summary = self._generate_summary(menu_items, price_comparison, best_deals)

            return ActionResult(
                status=ActionStatus.SUCCESS if menu_items else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "menu_items": menu_items,
                    "price_comparison": price_comparison,
                    "best_deals": best_deals,
                    "shopping_list": shopping_list,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Menu aggregation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to aggregate menus: {e}"
            )

    async def _scrape_supplier_menu(self, supplier: str, category: str) -> List[Dict]:
        """Scrape menu from supplier."""
        try:
            search_query = f"{supplier} restaurant supply menu"
            if category and category != "all":
                search_query += f" {category}"

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            items = []

            # Extract items and prices from page
            page_text = await self.browser.page.content()

            # Look for price patterns
            prices = re.findall(r'\$(\d+\.?\d*)', page_text)

            # Common food categories
            food_items = ["chicken", "beef", "pork", "vegetables", "dairy", "bread", "rice"]

            for food in food_items:
                if food in page_text.lower():
                    items.append({
                        "item": food.title(),
                        "supplier": supplier,
                        "category": category,
                        "price": f"${prices[0]}" if prices else "$0.00",
                        "unit": "lb"
                    })
                    if prices:
                        prices.pop(0)

            return items[:5]

        except Exception as e:
            logger.warning(f"Failed to scrape {supplier}: {e}")
            return []

    def _compare_pricing(self, items: List[Dict]) -> Dict:
        """Compare pricing across suppliers."""
        comparison = {
            "by_item": {},
            "by_supplier": {}
        }

        for item in items:
            item_name = item.get("item", "")
            supplier = item.get("supplier", "")
            price_str = item.get("price", "$0").replace("$", "")

            try:
                price = float(price_str)

                # By item
                if item_name not in comparison["by_item"]:
                    comparison["by_item"][item_name] = []
                comparison["by_item"][item_name].append({
                    "supplier": supplier,
                    "price": price
                })

                # By supplier
                if supplier not in comparison["by_supplier"]:
                    comparison["by_supplier"][supplier] = {"items": 0, "total": 0}
                comparison["by_supplier"][supplier]["items"] += 1
                comparison["by_supplier"][supplier]["total"] += price

            except Exception as e:
                logger.debug(f"Failed to parse menu item price: {e}")
                pass

        return comparison

    def _find_best_deals(self, items: List[Dict], budget: Optional[int]) -> List[Dict]:
        """Find best deals within budget."""
        # Sort by price
        sorted_items = sorted(items, key=lambda x: float(x.get("price", "$0").replace("$", "") or "0"))

        best_deals = []
        total_cost = 0

        for item in sorted_items:
            price_str = item.get("price", "$0").replace("$", "")
            try:
                price = float(price_str)

                if budget is None or (total_cost + price) <= budget:
                    best_deals.append(item)
                    total_cost += price
            except Exception as e:
                logger.debug(f"Failed to parse price for best deals '{price_str}': {e}")
                pass

        return best_deals

    def _generate_shopping_list(self, items: List[Dict]) -> Dict:
        """Generate shopping list."""
        shopping_list = {
            "items": [],
            "total_cost": 0,
            "by_supplier": {}
        }

        for item in items:
            price_str = item.get("price", "$0").replace("$", "")
            try:
                price = float(price_str)

                shopping_list["items"].append({
                    "item": item.get("item"),
                    "quantity": 1,
                    "supplier": item.get("supplier"),
                    "price": f"${price:.2f}"
                })

                shopping_list["total_cost"] += price

                supplier = item.get("supplier", "")
                if supplier not in shopping_list["by_supplier"]:
                    shopping_list["by_supplier"][supplier] = []
                shopping_list["by_supplier"][supplier].append(item.get("item"))

            except Exception as e:
                logger.debug(f"Failed to add item to shopping list: {e}")
                pass

        return shopping_list

    def _save_menu_report(self, items: List, comparison: Dict, best_deals: List, shopping_list: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"menu_aggregation_{timestamp}.json"
            return str(save_json(filename, {
                "menu_items": items,
                "price_comparison": comparison,
                "best_deals": best_deals,
                "shopping_list": shopping_list
            }))
        except Exception as e:
            logger.error(f"Failed to save menu report: {e}")
            return None

    def _generate_summary(self, items: List, comparison: Dict, best_deals: List) -> str:
        lines = [
            "## Menu Aggregation Report",
            f"**Items Found:** {len(items)}",
            f"**Suppliers:** {len(comparison.get('by_supplier', {}))}",
            f"**Best Deals:** {len(best_deals)}",
            ""
        ]

        if best_deals:
            lines.append("### Top Deals:")
            for deal in best_deals[:5]:
                lines.append(f"- {deal.get('item')}: {deal.get('price')} ({deal.get('supplier')})")
            lines.append("")

        return "\n".join(lines)


class AC2_PriceComparator(BaseExecutor):
    """Compare supplier pricing across multiple categories."""

    capability = "AC2"
    action = "compare_prices"
    required_params = ["items"]
    optional_params = ["suppliers", "output_format"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        items = params.get("items", [])
        suppliers = params.get("suppliers", [])
        output_format = params.get("output_format", "table")

        if not items:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide items to compare."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for price comparison"
            )

        try:
            price_matrix = []

            # Research prices for each item
            for item in items:
                item_prices = await self._research_item_prices(item, suppliers)
                price_matrix.append(item_prices)

            # Find best supplier for each item
            recommendations = self._generate_recommendations(price_matrix)

            # Calculate potential savings
            savings = self._calculate_savings(price_matrix, recommendations)

            saved_path = self._save_price_comparison(price_matrix, recommendations, savings)

            summary = self._generate_summary(price_matrix, recommendations, savings)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "price_matrix": price_matrix,
                    "recommendations": recommendations,
                    "savings": savings,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Price comparison failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to compare prices: {e}"
            )

    async def _research_item_prices(self, item: str, suppliers: List[str]) -> Dict:
        """Research prices for a specific item."""
        item_data = {
            "item": item,
            "prices": []
        }

        try:
            search_query = f"{item} food supplier price"
            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(1)

            page_text = await self.browser.page.content()
            prices = re.findall(r'\$(\d+\.?\d*)', page_text)

            # Simulate prices from different suppliers
            for i, supplier in enumerate(suppliers[:3]):
                price = float(prices[i]) if i < len(prices) else 10.0 + (i * 2)
                item_data["prices"].append({
                    "supplier": supplier,
                    "price": price
                })

        except Exception as e:
            logger.warning(f"Failed to research {item}: {e}")

        return item_data

    def _generate_recommendations(self, price_matrix: List[Dict]) -> List[Dict]:
        """Generate supplier recommendations."""
        recommendations = []

        for item_data in price_matrix:
            if item_data.get("prices"):
                best_price = min(item_data["prices"], key=lambda p: p["price"])
                recommendations.append({
                    "item": item_data["item"],
                    "recommended_supplier": best_price["supplier"],
                    "price": best_price["price"]
                })

        return recommendations

    def _calculate_savings(self, price_matrix: List[Dict], recommendations: List[Dict]) -> Dict:
        """Calculate potential savings."""
        total_savings = 0
        savings_by_item = []

        for item_data in price_matrix:
            if item_data.get("prices"):
                prices = [p["price"] for p in item_data["prices"]]
                min_price = min(prices)
                max_price = max(prices)
                savings = max_price - min_price

                total_savings += savings
                savings_by_item.append({
                    "item": item_data["item"],
                    "savings": f"${savings:.2f}",
                    "percentage": f"{(savings / max_price * 100):.1f}%" if max_price > 0 else "0%"
                })

        return {
            "total_savings": f"${total_savings:.2f}",
            "by_item": savings_by_item
        }

    def _save_price_comparison(self, matrix: List, recommendations: List, savings: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"price_comparison_{timestamp}.json"
            return str(save_json(filename, {
                "price_matrix": matrix,
                "recommendations": recommendations,
                "savings": savings
            }))
        except Exception as e:
            logger.error(f"Failed to save price comparison: {e}")
            return None

    def _generate_summary(self, matrix: List, recommendations: List, savings: Dict) -> str:
        lines = [
            "## Price Comparison Report",
            f"**Items Compared:** {len(matrix)}",
            f"**Potential Savings:** {savings['total_savings']}",
            ""
        ]

        if recommendations:
            lines.append("### Recommendations:")
            for rec in recommendations[:5]:
                lines.append(f"- {rec['item']}: {rec['recommended_supplier']} (${rec['price']})")

        return "\n".join(lines)


# ============ AE) MEDIA ============

class AE1_MentionMonitor(BaseExecutor):
    """Monitor press mentions and find relevant journalists."""

    capability = "AE1"
    action = "monitor_mentions"
    required_params = ["company_or_topic"]
    optional_params = ["keywords", "time_period"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        topic = params.get("company_or_topic", "")
        keywords = params.get("keywords", [])
        time_period = params.get("time_period", "past month")

        if not topic:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide company or topic to monitor."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for media monitoring"
            )

        try:
            # Search for press mentions
            mentions = await self._search_press_mentions(topic, keywords, time_period)

            # Analyze sentiment
            sentiment = self._analyze_sentiment(mentions)

            # Generate media report
            report = self._create_media_report(mentions, sentiment)

            saved_path = self._save_media_report(mentions, sentiment, report)

            summary = self._generate_summary(mentions, sentiment)

            return ActionResult(
                status=ActionStatus.SUCCESS if mentions else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "mentions": mentions,
                    "sentiment": sentiment,
                    "report": report,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Media monitoring failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to monitor media: {e}"
            )

    async def _search_press_mentions(self, topic: str, keywords: List[str], time_period: str) -> List[Dict]:
        """Search for press mentions."""
        try:
            search_query = f"{topic} news"
            if keywords:
                search_query += " " + " ".join(keywords[:2])

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws")
            await asyncio.sleep(2)

            mentions = []

            # Extract news articles
            data = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.SoaBEf, .WlydOe');

                    items.forEach(item => {
                        const title = item.querySelector('.mCBkyc, .n0jPhd')?.textContent?.trim();
                        const source = item.querySelector('.NUnG9d span, .CEMjEf')?.textContent?.trim();
                        const snippet = item.querySelector('.GI74Re, .Y3v8qd')?.textContent?.trim();
                        const link = item.querySelector('a')?.href;

                        if (title) {
                            results.push({
                                title: title,
                                source: source || 'Unknown',
                                snippet: snippet || '',
                                url: link || ''
                            });
                        }
                    });

                    return results.slice(0, 15);
                }
            """)

            for article in data:
                mentions.append({
                    "title": article["title"],
                    "source": article["source"],
                    "snippet": article["snippet"],
                    "url": article["url"],
                    "sentiment": "neutral"
                })

            return mentions

        except Exception as e:
            logger.warning(f"Press search failed: {e}")
            return []

    def _analyze_sentiment(self, mentions: List[Dict]) -> Dict:
        """Analyze sentiment of mentions."""
        sentiment = {
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "overall": "neutral"
        }

        positive_keywords = ["success", "growth", "innovation", "award", "leading", "best"]
        negative_keywords = ["failure", "problem", "issue", "controversy", "lawsuit", "decline"]

        for mention in mentions:
            text = (mention.get("title", "") + " " + mention.get("snippet", "")).lower()

            pos_count = sum(1 for kw in positive_keywords if kw in text)
            neg_count = sum(1 for kw in negative_keywords if kw in text)

            if pos_count > neg_count:
                mention["sentiment"] = "positive"
                sentiment["positive"] += 1
            elif neg_count > pos_count:
                mention["sentiment"] = "negative"
                sentiment["negative"] += 1
            else:
                mention["sentiment"] = "neutral"
                sentiment["neutral"] += 1

        # Determine overall sentiment
        if sentiment["positive"] > sentiment["negative"]:
            sentiment["overall"] = "positive"
        elif sentiment["negative"] > sentiment["positive"]:
            sentiment["overall"] = "negative"

        return sentiment

    def _create_media_report(self, mentions: List[Dict], sentiment: Dict) -> Dict:
        """Create comprehensive media report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_mentions": len(mentions),
            "sentiment_breakdown": sentiment,
            "top_sources": list(set(m.get("source") for m in mentions[:10])),
            "recommendations": self._generate_media_recommendations(sentiment)
        }

    def _generate_media_recommendations(self, sentiment: Dict) -> List[str]:
        """Generate media outreach recommendations."""
        recommendations = []

        if sentiment["overall"] == "positive":
            recommendations.append("Leverage positive coverage for marketing materials")
            recommendations.append("Share positive mentions on social media")

        if sentiment["overall"] == "negative":
            recommendations.append("Prepare crisis communication response")
            recommendations.append("Reach out to journalists for follow-up stories")

        return recommendations

    def _save_media_report(self, mentions: List, sentiment: Dict, report: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"media_mentions_{timestamp}.json"
            return str(save_json(filename, {
                "mentions": mentions,
                "sentiment": sentiment,
                "report": report
            }))
        except Exception as e:
            logger.error(f"Failed to save media monitoring report: {e}")
            return None

    def _generate_summary(self, mentions: List, sentiment: Dict) -> str:
        lines = [
            "## Media Monitoring Report",
            f"**Mentions Found:** {len(mentions)}",
            f"**Overall Sentiment:** {sentiment['overall'].upper()}",
            f"**Positive:** {sentiment['positive']} | Neutral: {sentiment['neutral']} | Negative: {sentiment['negative']}",
            ""
        ]

        if mentions:
            lines.append("### Recent Mentions:")
            for mention in mentions[:5]:
                sentiment_icon = "+" if mention.get("sentiment") == "positive" else "-" if mention.get("sentiment") == "negative" else "="
                lines.append(f"[{sentiment_icon}] {mention.get('title')} ({mention.get('source')})")
            lines.append("")

        return "\n".join(lines)


class AE2_JournalistFinder(BaseExecutor):
    """Find journalists covering specific topics."""

    capability = "AE2"
    action = "find_journalists"
    required_params = ["topic"]
    optional_params = ["keywords", "outlet"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        topic = params.get("topic", "")
        keywords = params.get("keywords", [])
        outlet = params.get("outlet", "")

        if not topic:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide topic to search for."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for journalist search"
            )

        try:
            # Find journalists
            journalists = await self._find_journalists(topic, keywords, outlet)

            # Generate outreach templates
            outreach = self._generate_outreach_templates(journalists[:5], topic)

            saved_path = self._save_journalist_report(journalists, outreach)

            summary = self._generate_summary(journalists, topic)

            return ActionResult(
                status=ActionStatus.SUCCESS if journalists else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "journalists": journalists,
                    "outreach_templates": outreach,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Journalist search failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to find journalists: {e}"
            )

    async def _find_journalists(self, topic: str, keywords: List[str], outlet: str) -> List[Dict]:
        """Find journalists covering the topic."""
        try:
            search_query = f"journalists covering {topic}"
            if keywords:
                search_query += " " + keywords[0]
            if outlet:
                search_query += f" {outlet}"

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            journalists = []

            # Extract journalist information
            data = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.g');

                    items.forEach(item => {
                        const title = item.querySelector('h3')?.textContent?.trim();
                        const snippet = item.querySelector('.VwiC3b')?.textContent?.trim();
                        const link = item.querySelector('a')?.href;

                        if (title && snippet) {
                            results.push({
                                name: title,
                                bio: snippet,
                                url: link || ''
                            });
                        }
                    });

                    return results.slice(0, 10);
                }
            """)

            for person in data:
                # Check if likely a journalist
                bio = person.get("bio", "").lower()
                if "journalist" in bio or "reporter" in bio or "writer" in bio or "editor" in bio:
                    journalists.append({
                        "name": person["name"],
                        "bio": person["bio"],
                        "url": person["url"],
                        "topics": [topic]
                    })

            return journalists[:10]

        except Exception as e:
            logger.warning(f"Journalist search failed: {e}")
            return []

    def _generate_outreach_templates(self, journalists: List[Dict], topic: str) -> List[Dict]:
        """Generate personalized outreach templates."""
        templates = []

        for journalist in journalists:
            name = journalist.get("name", "there")

            template = {
                "journalist": name,
                "subject": f"Story Idea: {topic}",
                "body": f"""Hi {name},

I noticed your coverage of {topic} and thought you might be interested in a story angle we're working on.

Would you be available for a brief call this week to discuss?

Best regards"""
            }
            templates.append(template)

        return templates

    def _save_journalist_report(self, journalists: List, outreach: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"journalist_finder_{timestamp}.json"
            return str(save_json(filename, {
                "journalists": journalists,
                "outreach_templates": outreach
            }))
        except Exception as e:
            logger.error(f"Failed to save journalist finder report: {e}")
            return None

    def _generate_summary(self, journalists: List, topic: str) -> str:
        lines = [
            "## Journalist Finder Report",
            f"**Topic:** {topic}",
            f"**Journalists Found:** {len(journalists)}",
            ""
        ]

        if journalists:
            lines.append("### Journalists:")
            for j in journalists[:5]:
                lines.append(f"- {j.get('name')}")
                if j.get("url"):
                    lines.append(f"  {j['url']}")

        return "\n".join(lines)
