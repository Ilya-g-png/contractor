from locust import HttpUser, task


class HealthUser(HttpUser):
    @task
    def health(self) -> None:
        self.client.get("/api/v1/health")
