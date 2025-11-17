```typescript
import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateTodoDto } from './dto/create-todo.dto';
import { UpdateTodoDto } from './dto/update-todo.dto';

@Injectable()
export class TodoService {
  constructor(private readonly prisma: PrismaService) {}

  async create(createTodoDto: CreateTodoDto) {
    try {
      return await this.prisma.todo.create({
        data: createTodoDto,
      });
    } catch (error) {
      throw new Error(`Failed to create todo: ${error.message}`);
    }
  }

  async findAll() {
    try {
      return await this.prisma.todo.findMany({
        orderBy: {
          createdAt: 'desc',
        },
      });
    } catch (error) {
      throw new Error(`Failed to retrieve todos: ${error.message}`);
    }
  }

  async findOne(id: number) {
    try {
      const todo = await this.prisma.todo.findUnique({
        where: { id },
      });

      if (!todo) {
        throw new NotFoundException(`Todo with ID ${id} not found`);
      }

      return todo;
    } catch (error) {
      if (error instanceof NotFoundException) {
        throw error;
      }
      throw new Error(`Failed to retrieve todo: ${error.message}`);
    }
  }

  async update(id: number, updateTodoDto: UpdateTodoDto) {
    try {
      await this.findOne(id);

      return await this.prisma.todo.update({
        where: { id },
        data: updateTodoDto,
      });
    } catch (error) {
      if (error instanceof NotFoundException) {
        throw error;
      }
      throw new Error(`Failed to update todo: ${error.message}`);
    }
  }

  async remove(id: number) {
    try {
      await this.findOne(id);

      return await this.prisma.todo.delete({
        where: { id },
      });
    } catch (error) {
      if (error instanceof NotFoundException) {
        throw error;
      }
      throw new Error(`Failed to delete todo: ${error.message}`);
    }
  }

  async findByStatus(completed: boolean) {
    try {
      return await this.prisma.todo.findMany({
        where: { completed },
        orderBy: {
          createdAt: 'desc',
        },
      });
    } catch (error) {
      throw new Error(`Failed to retrieve todos by status: ${error.message}`);
    }
  }

  async markAsCompleted(id: number) {
    try {
      await this.findOne(id);

      return await this.prisma.todo.update({
        where: { id },
        data: { completed: true },
      });
    } catch (error) {
      if (error instanceof NotFoundException) {
        throw error;
      }
      throw new Error(`Failed to mark todo as completed: ${error.message}`);
    }
  }

  async search(query: string) {
    try {
      return await this.prisma.todo.findMany({
        where: {
          OR: [
            {
              title: {
                contains: query,
                mode: 'insensitive',
              },
            },
            {
              description: {
                contains: query,
                mode: 'insensitive',
              },
            },
          ],
        },
        orderBy: {
          createdAt: 'desc',
        },
      });
    } catch (error) {
      throw new Error(`Failed to search todos: ${error.message}`);
    }
  }
}
```