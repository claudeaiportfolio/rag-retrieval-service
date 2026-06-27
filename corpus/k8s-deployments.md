# Deployments

A Deployment provides declarative updates for Pods and ReplicaSets.

You describe a desired state in a Deployment, and the Deployment Controller changes the actual state to the desired state at a controlled rate. You can define Deployments to create new ReplicaSets, or to remove existing Deployments and adopt all their resources with new Deployments.

## Use case

The following are typical use cases for Deployments:

- Create a Deployment to rollout a ReplicaSet. The ReplicaSet creates Pods in the background.
- Declare the new state of the Pods by updating the PodTemplateSpec of the Deployment. A new ReplicaSet is created and the Deployment manages moving the Pods from the old ReplicaSet to the new one at a controlled rate. Each new ReplicaSet updates the revision of the Deployment.
- Rollback to an earlier Deployment revision if the current state of the Deployment is not stable.
- Scale up the Deployment to facilitate more load.
- Pause the rollout of a Deployment to apply multiple fixes to its PodTemplateSpec and then resume it to start a new rollout.
- Clean up older ReplicaSets that you don't need anymore.

## Updating a Deployment

A Deployment's rollout is triggered if and only if the Deployment's Pod template (`.spec.template`) is changed, for example if the labels or container images of the template are updated.

Rolling updates allow Deployments' update to take place with zero downtime by incrementally updating Pod instances with new ones.

## Rolling Back a Deployment

Sometimes, you may want to rollback a Deployment; for example, when the Deployment is not stable, such as crash looping. By default, all of the Deployment's rollout history is kept in the system so that you can rollback anytime you want.

Use `kubectl rollout undo deployment/<name>` to roll back to the previous revision.

## Scaling a Deployment

You can scale a Deployment by using the following command: `kubectl scale deployment/<name> --replicas=10`.

## Pod and Container Field References

A Deployment's Pod template uses the standard PodSpec. The container image is the most commonly updated field, and triggers a new rollout.
